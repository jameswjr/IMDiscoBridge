# IMDiscoBridge Installation & Configuration Guide (Experimental Use Only)

> **WARNING:** This is **experimental software**. It interfaces with system-level Apple Messages data using AppleScript and direct SQLite queries. It has not been audited for security, privacy, or long-term stability. **Use at your own risk.**

> 🚧 STILL UNTESTED — This is a preview of a development project.
This notice will be removed when the system passes its first successful test.

> This tool **does not** collect or transmit data anywhere except to your configured Discord server.

---

## What This Does

IMDiscoBridge:
- Reads your iMessage history on macOS via the `chat.db` file
- Sends incoming messages to Discord
- Lets you reply from Discord back into iMessage, as if you sent it from Messages.app

---

## Pre-Installation Requirements

### Hardware/OS
- A Mac running macOS Monterey or later
- Logged into Messages.app with your Apple ID (email-based)

### Software
- Python 3.8 or later (`python3 --version`)
- Terminal access

### Discord Setup (Required)

### 1. Create a Discord Server
- Open [https://discord.com](https://discord.com)
- Click the `+` button in the server list (left sidebar)
- Choose “Create My Own”
- Name it (e.g., `IMDiscoBridge Server`)
- Set it to Private (recommended)

### 2. Create a Discord Bot

- Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
- Click **"New Application"** and name it something like `IMDiscoBridgeBot`
- Go to **Bot** (left sidebar) → click **"Add Bot"**
- Under **Privileged Gateway Intents**, **enable**:
  - `MESSAGE CONTENT INTENT`
- Copy the bot **token** (you’ll paste this into your `config.json` later)

### 3. Invite the Bot to Your Server

- Go to **OAuth2 > URL Generator**
  - Scopes: check `bot`
  - Bot Permissions: check
    - `View Channels`
    - `Send Messages`
    - `Read Message History`
    - `Manage Channels`
- Copy the generated URL and visit it in your browser
- Select your Discord server to invite the bot

---

## Installation Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/YOURNAME/IMDiscoBridge.git
cd IMDiscoBridge
```

### 2. Set Up Project Structure

```bash
mkdir -p ~/imdiscobridge/{config,state}
cp -r scripts launch config README.md ~/imdiscobridge/
cp config/config.example.json ~/imdiscobridge/config/config.json
```

### 3. Python Environment Setup (Recommended)

**You must install and use IMDiscoBridge within a Python virtual environment.**
All instructions and system integration (including MacOS auto-start) assume this setup.

```bash
cd ~/imdiscobridge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

To exit the virtual environment later:

```bash
deactivate
```

> Dependencies are listed in `requirements.txt`, including `requests` and `discord.py`.

## Configuration and Use

### 1. Copy and Edit Your Config File

The repo provides a template config file. If you did not copy it earlier, do so now:

```bash
cp ~/imdiscobridge/config/config.example.json ~/imdiscobridge/config/config.json
```

Then edit `~/imdiscobridge/config/config.json`:

```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/dummy",
  "discord_bot_token": "your-bot-token",
  "default_guild_id": "your-guild-id",
  "user_id_whitelist": [],
  "poll_interval_seconds": 10,
  "burst_trigger_count": 8,
  "burst_window_seconds": 10,
  "burst_poll_interval": 0.5,
  "active_poll_interval": 10,
  "default_poll_interval": 30,
  "global_discovery_interval": 15,
  "whitelisted_chats": []
}
```

### Key Fields:
- `discord_bot_token`: Get this from the [Discord Developer Portal](https://discord.com/developers/applications)
- `default_guild_id`: Right-click your server in Discord → "Copy Server ID"
- `user_id_whitelist`: List of Discord user IDs allowed to send messages back (leave empty for all)
- `whitelisted_chats`: Restrict forwarding to certain iMessage threads (safe for testing, also for restricted use)
- `poll_interval_seconds`: How often to check the DB
- `burst_poll_interval`: Fastest polling interval in “burst mode”
- `active_poll_interval`: Interval for chats recently active
- `default_poll_interval`: Used for quiet/inactive chats

Start in test mode with 1–2 whitelisted chats:

```json
{
  "whitelisted_chats": ["iMessage;chat123abc"]
}
```

---

### 2. Run Manually (Test Mode)

```bash
# Terminal 1
python3 ~/imdiscobridge/scripts/forwarder.py

# Terminal 2
python3 ~/imdiscobridge/scripts/responder.py
```

Note: Each time you open a new terminal session, you’ll need to reactivate the virtual environment (venv), if you used that:

```bash
source ~/imdiscobridge/venv/bin/activate
```

---

## Going Live (Enable All Chats)

Update `config.json`:

```json
"whitelisted_chats": [],
"user_id_whitelist": []
```

---

## Auto-Start on Login (macOS)

### 1. Copy Launch Agent Files

```bash
cp launch/com.imdiscobridge.*.plist ~/Library/LaunchAgents/
```

### 2. Customize Launch Files

IMPORTANT: The launch plist files need your macOS username, so
you must update the paths in each .plist file to reflect your actual home directory.

For example, in the ProgramArguments section of your .plist, change:

<string>/Users/YOURUSERNAME/imdiscobridge/venv/bin/python</string>
<string>/Users/YOURUSERNAME/imdiscobridge/scripts/forwarder.py</string>

...to:

<string>/Users/YOUR_ACTUAL_USERNAME/imdiscobridge/venv/bin/python</string>
<string>/Users/YOUR_ACTUAL_USERNAME/imdiscobridge/scripts/forwarder.py</string>

You can edit the .plist files with a text editor before installing them:

nano launch/com.imdiscobridge.forwarder.plist

### 3. Load with `launchctl`

```bash
launchctl load ~/Library/LaunchAgents/com.imdiscobridge.forwarder.plist
launchctl load ~/Library/LaunchAgents/com.imdiscobridge.responder.plist
```

### 4. Confirm everything works:

```
launchctl list | grep imdiscobridge
```

To stop or reload:

```
launchctl unload ~/Library/LaunchAgents/com.imdiscobridge.forwarder.plist
launchctl unload ~/Library/LaunchAgents/com.imdiscobridge.responder.plist
```

---

## Troubleshooting

- Messages not forwarding? Open Messages.app and ensure it’s signed in.
- Replies not sending? Test AppleScript:
  ```bash
  osascript -e 'tell application "Messages" to send "test" to chat id "iMessage;chatABC123"'
  ```
- Bot unresponsive? Verify config settings and bot permissions.

---

## ⚠️ Security

- **ALL YOUR IMESSAGES ARE SENT TO DISCORD!!!**  
  **BE SURE YOU WANT TO DO THAT.**  
  Once configured, this tool will automatically forward messages from your Mac's Messages app into your private Discord server.  
  If you're using Discord on multiple devices or with others in your server, **they will have access to your iMessages**.
  You can restrict which chats are forwarded.

- All activity stays local to your Mac — this tool does not run any servers or send data to third parties **outside of Discord**.

- No credentials stored beyond Discord token

- Your Apple ID credentials are never accessed or stored.

- No external cloud storage or logs are used — everything happens locally.

---

## License

MIT — See LICENSE
