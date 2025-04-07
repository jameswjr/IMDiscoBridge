import os
import json
import time
import fcntl  # For file locking
import tempfile  # For atomic writes
import sqlite3
import requests
import logging
from datetime import datetime, timedelta
from collections import deque
import random
import asyncio

# Define base directory relative to the script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define deterministic paths
LOG_DIR = os.path.join(BASE_DIR, "../logs")
LOG_FILE = os.path.join(LOG_DIR, "forwarder.log")

# Ensure the log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Define deterministic paths
CONFIG_PATH = os.path.join(BASE_DIR, "../config/config.json")
STATE_PATH = os.path.join(BASE_DIR, "../state/state.json")
CHAT_DB_PATH = "/Library/Messages/chat.db"  # Fixed path for iMessage database on macOS

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Retry decorator with exponential backoff
def exponential_backoff(retries=5, base_delay=1, max_delay=16, jitter=True):
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries:
                        logger.error(f"All {retries} attempts failed for {func.__name__}: {e}")
                        raise
                    logger.warning(f"Attempt {attempt} failed for {func.__name__}: {e}. Retrying in {delay} seconds...")
                    if jitter:
                        delay += random.uniform(0, base_delay)  # Add jitter to avoid thundering herd
                    time.sleep(min(delay, max_delay))
                    delay *= 2  # Exponential backoff
        return wrapper
    return decorator

# Load JSON with backup for corrupted files
def load_json_with_backup(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading JSON from {path}: {e}")
        backup_path = f"{path}.backup"
        if os.path.exists(path):
            os.rename(path, backup_path)  # Backup corrupted file
            logger.warning(f"Backed up corrupted file to {backup_path}")
    return {}

    # Ensure "chats" key exists in the state
    if "chats" not in state:
        state["chats"] = {}
    return state

# Save JSON with error handling
def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to save JSON to {path}: {e}")

# Escape special characters in Discord messages
def notify_admin(bot_token, admin_channel_id, message):
    try:
        sanitized_message = message.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
        url = f"https://discord.com/api/v10/channels/{admin_channel_id}/messages"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
        payload = {"content": f"**Fatal Error:** {sanitized_message}"}
        requests.post(url, headers=headers, json=payload)
    except requests.RequestException as e:
        logger.error(f"Failed to notify admin: {e}")

# Validate configuration
def validate_config(config):
    required_keys = ["discord_bot_token", "default_guild_id", "default_poll_interval"]
    for key in required_keys:
        if key not in config:
            logger.critical(f"Missing required configuration key: {key}")
            return False
    return True

# Retry database connection with exponential backoff
@exponential_backoff(retries=5, base_delay=1, max_delay=16)
def connect_to_database(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")  # Enable Write-Ahead Logging
    logger.info("Connected to the database with WAL mode enabled.")
    return conn

def get_display_name(chat_db, handle_id):
    try:
        query = "SELECT id FROM handle WHERE id = ?"
        cursor = chat_db.cursor()
        cursor.execute(query, (handle_id,))
        result = cursor.fetchone()
        return result[0] if result else handle_id
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching display name for handle_id {handle_id}: {e}")
        return handle_id

def get_chat_participants(chat_db, chat_guid):
    try:
        query = """
        SELECT h.id
        FROM chat c
        JOIN chat_handle_join chj ON c.ROWID = chj.chat_id
        JOIN handle h ON chj.handle_id = h.ROWID
        WHERE c.guid = ?
        """
        cursor = chat_db.cursor()
        cursor.execute(query, (chat_guid,))
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching participants for chat {chat_guid}: {e}")
        return []

def create_discord_channel(bot_token, guild_id, name, participants):
    try:
        url = f"https://discord.com/api/v10/guilds/{guild_id}/channels"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
        channel_name = name.lower().replace(" ", "-")[:100]
        payload = {
            "name": channel_name,
            "type": 0
        }
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 201:
            channel = response.json()
            logger.info(f"Created Discord channel: {channel['name']} (ID: {channel['id']})")
            return channel["id"]
        else:
            logger.error(f"Failed to create channel: {response.status_code} - {response.text}")
            return None
    except requests.RequestException as e:
        logger.error(f"HTTP error while creating Discord channel: {e}")
        return None

def send_to_discord_channel(bot_token, channel_id, content):
    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
        payload = {"content": content}
        while True:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200 or response.status_code == 204:
                return True  # Message sent successfully
            elif response.status_code == 429:  # Rate-limited
                retry_after = float(response.headers.get("Retry-After", 1))  # Default to 1 second if missing
                logger.warning(f"Rate-limited by Discord. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                logger.error(f"Failed to send message to Discord channel {channel_id}: {response.status_code} - {response.text}")
                return False
    except requests.RequestException as e:
        logger.error(f"HTTP error while sending message to Discord channel {channel_id}: {e}")
        return False

def send_to_discord(webhook_url, sender, message_text, timestamp, chat_guid):
    try:
        content = f"[{sender} @ {timestamp}]: {message_text}"
        payload = {
            "username": chat_guid,
            "content": content
        }
        while True:
            response = requests.post(webhook_url, json=payload)
            if response.status_code == 204:
                return True  # Message sent successfully
            elif response.status_code == 429:  # Rate-limited
                retry_after = float(response.headers.get("Retry-After", 1))  # Default to 1 second if missing
                logger.warning(f"Rate-limited by Discord webhook. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                logger.error(f"Failed to send message via webhook: {response.status_code} - {response.text}")
                return False
    except requests.RequestException as e:
        logger.error(f"HTTP error while sending message via webhook: {e}")
        return False

def get_active_chats(chat_db, since_time):
    try:
        query = f"""
        SELECT
            c.guid,
            MAX(m.date) as last_date
        FROM chat c
        JOIN chat_message_join cmj ON c.ROWID = cmj.chat_id
        JOIN message m ON m.ROWID = cmj.message_id
        GROUP BY c.guid
        HAVING last_date > {(since_time - datetime(2001, 1, 1)).timestamp()}
        """
        cursor = chat_db.cursor()
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            logger.warning("Database locked while fetching active chats. Retrying...")
        return []

def get_new_messages(chat_db, guid, last_seen_rowid):
    try:
        query = f"""
        SELECT
            m.ROWID,
            datetime(m.date/1000000000 + strftime('%s','2001-01-01'), 'unixepoch') AS message_time,
            h.id,
            m.text
        FROM chat c
        JOIN chat_message_join cmj ON c.ROWID = cmj.chat_id
        JOIN message m ON m.ROWID = cmj.message_id
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        WHERE c.guid = ?
        AND m.ROWID > ?
        ORDER BY m.ROWID ASC
        """
        cursor = chat_db.cursor()
        cursor.execute(query, (guid, last_seen_rowid))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching new messages for chat {guid}: {e}")
        return []

def burst_check(message_times, now, threshold_count, window_seconds):
    cutoff = now - timedelta(seconds=window_seconds)
    while message_times and datetime.fromisoformat(message_times[0]) < cutoff:
        message_times.popleft()
    return len(message_times) >= threshold_count

def update_state_file(state, chat_guid, discord_channel_id, default_poll_interval):
    state["chats"][chat_guid] = {
        "discord_channel_id": discord_channel_id,
        "last_seen_rowid": 0,
        "poll_interval": default_poll_interval,
        "message_times": [],
        "burst_mode": False,
        "last_polled": "1970-01-01T00:00:00",
        "active_until": datetime.utcnow().isoformat(),
        "last_name_check": "1970-01-01T00:00:00"
    }
    save_json(STATE_PATH, state)
    logger.info(f"Updated state.json with new chat: {chat_guid} → {discord_channel_id}")

# Sanitize AppleScript inputs
async def send_imessage_async(chat_guid, message):
    script = '''
on run {chatID, messageText}
    set safeMessage to quoted form of messageText
    tell application "Messages"
        send safeMessage to chat id chatID
    end tell
end run
'''
    process = await asyncio.create_subprocess_exec(
        "osascript", "-e", script, "--args", chat_guid, message,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(f"AppleScript error: {stderr.decode().strip()}")
        return False
    return True

# Read the state file with a shared lock and retries
def read_state_file(state_path, retries=10, delay=0.1):
    for attempt in range(1, retries + 1):
        try:
            with open(state_path, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)  # Acquire a shared lock
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)  # Release the lock
        except BlockingIOError:
            if attempt < retries:
                logger.warning(f"State file locked (attempt {attempt}/{retries}). Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error("Failed to acquire shared lock on state file after multiple attempts.")
                raise

# Write the state file atomically with an exclusive lock and retries
def write_state_file(state_path, data, retries=10, delay=0.1):
    temp_dir = os.path.dirname(state_path)
    with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())  # Ensure data is written to disk
        temp_path = tmp.name

    for attempt in range(1, retries + 1):
        try:
            with open(state_path, "a") as f:
                fcntl.flock(f, fcntl.LOCK_EX)  # Acquire an exclusive lock
                try:
                    os.rename(temp_path, state_path)  # Atomically replace the file
                    return
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)  # Release the lock
        except BlockingIOError:
            if attempt < retries:
                logger.warning(f"State file locked for writing (attempt {attempt}/{retries}). Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error("Failed to acquire exclusive lock on state file after multiple attempts.")
                raise

def main():
    # Load configuration and state
    config = load_json_with_backup(CONFIG_PATH)
    if not validate_config(config):
        logger.critical("Invalid configuration. Exiting.")
        return

    state = load_json_with_backup(STATE_PATH)
    if not state:
        logger.critical("Failed to load state.json. System is non-functional.")
        return

    # Ensure "chats" key exists in the state
    if "chats" not in state:
        state["chats"] = {}

    # Load configuration values
    webhook_url = config.get("discord_webhook_url")
    bot_token = config["discord_bot_token"]
    guild_id = config["default_guild_id"]
    admin_channel_id = config.get("admin_channel_id")  # Optional: for notifications
    whitelisted_chats = config.get("whitelisted_chats", [])
    burst_trigger_count = config.get("burst_trigger_count", 8)
    burst_window_seconds = config.get("burst_window_seconds", 10)
    burst_poll_interval = config.get("burst_poll_interval", 0.5)
    active_poll_interval = config.get("active_poll_interval", 10)
    default_poll_interval = config.get("default_poll_interval", 30)
    discovery_interval = config.get("global_discovery_interval", 15)

    # Check if the iMessage database exists
    if not os.path.exists(CHAT_DB_PATH):
        logger.critical("iMessage database not found. System is non-functional.")
        if admin_channel_id:
            notify_admin(bot_token, admin_channel_id, "iMessage database not found. System is non-functional.")
        return

    # Connect to the iMessage database
    try:
        conn = connect_to_database(CHAT_DB_PATH)
    except sqlite3.Error as e:
        logger.critical(f"Failed to connect to iMessage database: {e}")
        if admin_channel_id:
            notify_admin(bot_token, admin_channel_id, f"Failed to connect to iMessage database: {e}")
        return

    while True:
        now = datetime.utcnow()
        if state.get("last_global_poll") is None:
            state["last_global_poll"] = (now - timedelta(days=1)).isoformat()

        # Perform global discovery at intervals
        if (now - datetime.fromisoformat(state["last_global_poll"])).total_seconds() >= discovery_interval:
            active_chats = get_active_chats(conn, now - timedelta(days=1))
            for chat_guid in active_chats:
                if whitelisted_chats and chat_guid not in whitelisted_chats:
                    continue
                chat_state = state["chats"].setdefault(chat_guid, {
                    "last_seen_rowid": 0,
                    "poll_interval": default_poll_interval,
                    "message_times": [],
                    "burst_mode": False,
                    "last_polled": "1970-01-01T00:00:00",
                    "active_until": now.isoformat(),
                    "last_name_check": "1970-01-01T00:00:00"
                })
                if "discord_channel_id" not in chat_state:
                    participants = get_chat_participants(conn, chat_guid)
                    channel_name = "chat-" + "-".join(p.split("@")[0] for p in participants)[:80]
                    channel_id = create_discord_channel(bot_token, guild_id, channel_name, participants)
                    if channel_id:
                        chat_state["discord_channel_id"] = str(channel_id)
                        welcome = f"[Bridge initialized for iMessage chat with: {', '.join(participants)}]"
                        send_to_discord_channel(bot_token, channel_id, welcome)
                        update_state_file(state, chat_guid, channel_id, default_poll_interval)
            state["last_global_poll"] = now.isoformat()

        soonest_next_poll = now + timedelta(seconds=default_poll_interval)

        for chat_guid, chat_state in state["chats"].items():
            if whitelisted_chats and chat_guid not in whitelisted_chats:
                continue

            # Determine the chat's state and set the polling interval
            active_until = datetime.fromisoformat(chat_state.get("active_until", "1970-01-01T00:00:00"))
            if chat_state["burst_mode"]:
                chat_state["poll_interval"] = burst_poll_interval
            elif now <= active_until:
                chat_state["poll_interval"] = active_poll_interval
            else:
                chat_state["poll_interval"] = default_poll_interval

            # Calculate the next poll time
            next_poll_time = datetime.fromisoformat(chat_state["last_polled"]) + timedelta(seconds=chat_state["poll_interval"])
            if next_poll_time < now:
                next_poll_time = now + timedelta(seconds=chat_state["poll_interval"])
            if now < next_poll_time:
                soonest_next_poll = min(soonest_next_poll, next_poll_time)
                continue

            # Fetch new messages for the chat
            messages = get_new_messages(conn, chat_guid, chat_state["last_seen_rowid"])
            chat_state["last_polled"] = now.isoformat()

            for rowid, timestamp, sender, text in messages:
                if text:
                    channel_id = chat_state.get("discord_channel_id")
                    if channel_id:
                        send_to_discord_channel(bot_token, channel_id, f"[{sender} @ {timestamp}]: {text}")
                    chat_state["last_seen_rowid"] = rowid
                    chat_state["active_until"] = (now + timedelta(minutes=10)).isoformat()
                    chat_state["message_times"].append(timestamp)

                    # Check for name changes
                    last_name_check = datetime.fromisoformat(chat_state.get("last_name_check", "1970-01-01T00:00:00"))
                    name_check_interval = timedelta(minutes=1 if chat_state["burst_mode"] else 5)
                    if now - last_name_check >= name_check_interval:
                        current_name = get_display_name(conn, sender or "You")
                        cached_name = state.setdefault("display_names", {}).get(sender, current_name)
                        if current_name != cached_name:
                            state["display_names"][sender] = current_name
                            name_change_notice = f"[{sender} is now known as {current_name}.]"
                            send_to_discord_channel(bot_token, channel_id, name_change_notice)
                        chat_state["last_name_check"] = now.isoformat()

            # Update burst mode and message times
            times = deque(chat_state["message_times"], maxlen=100)
            chat_state["burst_mode"] = burst_check(times, now, burst_trigger_count, burst_window_seconds)
            chat_state["message_times"] = list(times)

        # Save state after processing all chats
        save_json(STATE_PATH, state)

        # Sleep until the soonest next poll time
        sleep_duration = max(0.1, (soonest_next_poll - datetime.utcnow()).total_seconds())
        time.sleep(sleep_duration)

if __name__ == "__main__":
    main()
