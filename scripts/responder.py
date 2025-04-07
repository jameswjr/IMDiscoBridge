import os
import json
import asyncio
import subprocess
import discord
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Define base directory relative to the script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define deterministic paths
LOG_DIR = os.path.join(BASE_DIR, "../logs")
LOG_FILE = os.path.join(LOG_DIR, "responder.log")

# Ensure the log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

CONFIG_PATH = os.path.join(BASE_DIR, "../config/config.json")
STATE_PATH = os.path.join(BASE_DIR, "../state/state.json")

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load JSON with backup for corrupted files
def load_json_with_backup(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading JSON from {path}: {e}")
        backup_path = f"{path}.backup"
        if os.path.exists(path):
            os.rename(path, backup_path)
            logger.warning(f"Backed up corrupted file to {backup_path}")
        return {"chats": {}}  # Initialize default state

# Validate configuration
def validate_config(config):
    required_keys = ["discord_bot_token"]
    for key in required_keys:
        if key not in config:
            logger.critical(f"Missing required configuration key: {key}")
            return False
    return True

config = load_json_with_backup(CONFIG_PATH)
if not validate_config(config):
    logger.critical("Invalid configuration. Exiting.")
    exit(1)

state = load_json_with_backup(STATE_PATH)

# Build Discord channel ID → iMessage GUID map
channel_to_chat = state.get("chats", {})  # Ensure "chats" key exists
for chat_guid, chat_info in state.get("chats", {}).items():
    if "discord_channel_id" in chat_info:
        channel_to_chat[str(chat_info["discord_channel_id"])] = chat_guid

discord_token = config["discord_bot_token"]
user_whitelist = config.get("user_id_whitelist", [])  # Optional: list of Discord user IDs allowed to reply

# Setup Discord client
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)

state_lock = asyncio.Lock()

async def reload_state():
    global state, channel_to_chat
    try:
        async with state_lock:
            state = load_json_with_backup(STATE_PATH)
            channel_to_chat = {
                str(chat_info["discord_channel_id"]): chat_guid
                for chat_guid, chat_info in state.get("chats", {}).items()
                if "discord_channel_id" in chat_info
            }
            logger.info("State reloaded.")
    except Exception as e:
        logger.error(f"Failed to reload state: {e}")

class StateFileChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("state.json"):
            asyncio.run_coroutine_threadsafe(reload_state(), asyncio.get_event_loop())
            logger.info("State file changed. Reloaded state.")

def start_file_watcher():
    event_handler = StateFileChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(STATE_PATH), recursive=False)
    observer.start()
    logger.info("Started watching state.json for changes.")
    return observer

@client.event
async def on_ready():
    logger.info(f"Responder is online as {client.user}.")
    await reload_state()

@client.event
async def on_message(message):
    try:
        if message.author.bot:
            return

        if user_whitelist and str(message.author.id) not in user_whitelist:
            try:
                await message.author.send("You are not authorized to use this bot.")
            except discord.Forbidden:
                logger.warning(f"Could not send DM to user {message.author.id}.")
            return

        channel_id = str(message.channel.id)
        if channel_id not in channel_to_chat:
            return

        chat_guid = channel_to_chat[channel_id]
        success = await send_imessage_async(chat_guid, message.content)
        if success:
            logger.info(f"Relayed from Discord: '{message.content}' → {chat_guid}")
        else:
            await message.channel.send("**Error:** Failed to send iMessage from bot.")
    except Exception as e:
        logger.error(f"Error handling message: {e}")

async def send_imessage_async(chat_guid, message):
    sanitized_message = message.replace('"', '\\"').replace("\\", "\\\\").replace("\n", "\\n")
    if len(sanitized_message) > 1000:  # Example limit
        sanitized_message = sanitized_message[:997] + "..."
        logger.warning("Message truncated due to excessive length.")
    script = f'''
    tell application "Messages"
        send "{sanitized_message}" to chat id "{chat_guid}"
    end tell
    '''
    process = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(f"AppleScript error: {stderr.decode().strip()}")
        return False
    return True

async def shutdown(observer):
    logger.info("Shutting down responder...")
    observer.stop()
    observer.join()  # Wait for the observer thread to finish
    await client.close()  # Close the Discord client
    logger.info("Responder shut down gracefully.")

if __name__ == "__main__":
    observer = start_file_watcher()
    try:
        client.run(discord_token)
    except KeyboardInterrupt:
        asyncio.run(shutdown(observer))
