# Telegram Auto Admin Bot

Features:
- Automatically approves join requests in chats where the bot has the required admin permissions.
- Sends a personal welcome DM with two inline buttons.
- Detects member departures and sends a professional rejoin message.
- Creates a fresh invite link when Telegram permissions allow; public username is used as a fallback.
- Admin commands: `/status`, `/stats`, `/test`.
- Health endpoints: `/` and `/health`.
- Stores counters in `data.json` (no external database).

## GitHub setup
1. Create a new GitHub repository.
2. Upload `bot.py`, `requirements.txt`, `render.yaml`, `.gitignore`, and this README.
3. Do **not** upload your real `.env` file or bot token. `.env.example` is only a template.
4. In Render, create a Web Service from the repository. You can use `render.yaml` or set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python bot.py`
5. Add environment variables in Render: `BOT_TOKEN`, `ADMIN_ID`, `LINKS_CHANNEL`, and `SUPPORT_URL`.
6. Make the bot an administrator in each channel/group where it should work. Enable permission to invite users/manage invite links and ensure it can manage join requests.
7. Open the bot in Telegram and send `/start`. The admin can use `/stats`, `/status`, and `/test`.

## Environment variables
- `BOT_TOKEN`: token from BotFather.
- `ADMIN_ID`: your numeric Telegram user ID.
- `LINKS_CHANNEL`: URL for the channel directory.
- `SUPPORT_URL`: support/contact URL.
- `PORT`: Render sets this automatically; default is 10000.
- `DATA_FILE`: JSON data file path; default is `data.json`.

## Important notes
- Telegram does not allow a bot to send a private message to a user unless the user has started the bot or otherwise opened a private chat with it. Welcome/leave DMs can therefore fail for users who have never started the bot.
- The stats are not historical Telegram-wide totals. They count events observed by this bot after this version starts tracking.
- Free Render services may use ephemeral storage. If the service restarts or redeploys, `data.json` may reset. For persistent statistics, attach a persistent disk (if your plan supports it) and set `DATA_FILE` to a path on that disk.
- If you use a public group/channel, the bot may fall back to its public URL if it cannot create an invite link.
- Avoid committing secrets to GitHub.
