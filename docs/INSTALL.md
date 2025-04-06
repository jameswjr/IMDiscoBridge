# IMDiscoBridge Installation & Configuration Guide (Experimental Use Only)

> **WARNING:** This is **experimental software**. It interfaces with system-level Apple Messages data using AppleScript and direct SQLite queries. It has not been audited for security, privacy, or long-term stability. **Use at your own risk.**

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

### External Setup
1. Create a Discord Server for private use
2. Create a Discord Bot at https://discord.com/developers/applications
   - Enable MESSAGE CONTENT INTENT
   - Generate a bot token
   - Invite the bot to your server using OAuth2 with permissions:
     - Manage Channels
     - Send Messages
     - Read Message History
     - View Channels

---

## Installation Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/YOURNAME/IMDiscoBridge.git
cd IMDiscoBridge
```

### 2. Set Up Project Structure

```bash
mkdir -p ~/improxy/{config,state}
cp -r scripts launch config README.md ~/improxy/
cp config/config.example.json ~/improxy/config/config.json
```

---

## Configuration

### 1. Edit `~/improxy/config/config.json`

Start in test mode with 1–2 whitelisted chats:

```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/dummy",
  "discord_bot_token": "YOUR_DISCORD_BOT_TOKEN",
  "default_guild_id": "YOUR_DISCORD_SERVER_ID",
  "user_id_whitelist": ["YOUR_DISCORD_USER_ID"],
  "whitelisted_chats": ["iMessage;chat123abc"]
}
```

---

### 2. Run Manually (Test Mode)

```bash
# Terminal 1
python3 ~/improxy/scripts/forwarder.py

# Terminal 2
python3 ~/improxy/scripts/responder.py
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
cp launch/com.improxy.*.plist ~/Library/LaunchAgents/
```

### 2. Load with `launchctl`

```bash
launchctl load ~/Library/LaunchAgents/com.improxy.forwarder.plist
launchctl load ~/Library/LaunchAgents/com.improxy.responder.plist
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

## Security

- All activity stays local to your Mac
- No credentials stored beyond Discord token
- Apple ID password is never accessed

---

## License

MIT — See LICENSE
