<p align="center">
  <img src="assets/imdiscobridge-logo.png" width="300" alt="IMDiscoBridge logo" />
</p>

#  IMDiscoBridge 💬✨
##  iMessage ↔ Discord Bridge for macOS

**IMDiscoBridge** is an experimental bridge that allows forwarding iMessages from your Mac into Discord channels, and replying to them from Discord back into iMessage. It runs entirely on your Mac, using AppleScript and local SQLite queries.

> **WARNING: This is experimental software.**  
> It manipulates local iMessage state using AppleScript and reads from system-level SQLite databases. Use with care. No data is sent to any server besides your Discord instance.

---

## Features

**🚧 STILL UNTESTED — This is a preview of a development project.**  
This notice will be removed when the system passes its first successful test.  
**Use at your own risk!**

- Full iMessage message forwarding into Discord
- Replies from Discord sent back into iMessage
- Dynamic Discord channel creation
- Adaptive polling and burst mode support
- Display name change detection
- Safe test-first configuration
- Auto-launch on macOS startup (optional)

---

## Requirements

- macOS with Messages.app signed in to your Apple ID
- Python 3.8+
- Access to the Terminal
- A Discord bot + server

---

### Install & Configure

See [docs/INSTALL.md](docs/INSTALL.md) for full instructions including Discord bot setup, test mode, and macOS auto-start.

