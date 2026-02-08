# Usage Guide

For installation and basic setup, see [README.md](../README.md).

## Getting Telegram API Keys

1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click "API development tools"
4. Fill in app details (App title, Short name)
5. Save your API ID and API Hash

## Telegram Authentication

On first run:
1. Go to the **Auth** tab in the web UI (`http://127.0.0.1:5000`)
2. When the status shows "Waiting for code", enter the verification code sent to your Telegram
3. If two-factor authentication (2FA) is enabled, a password input form will appear

After authentication, a `data/bot_session.session` file is created and subsequent runs won't require re-authentication.

## Manual Message Reply

You can send messages directly to a conversation partner from the web UI:

1. Click a **recent conversation** in the sidebar on the Conversations tab
2. Only messages with that person will be displayed
3. Type your message in the input field at the bottom
4. Click the **Send** button or press `Enter` (`Shift+Enter` for newline)
5. Use the **back** button to return to the full conversation list

> Manual reply is only available when the bot is authenticated.

## Troubleshooting

### "Not Configured" status keeps showing
- Verify that API ID, API Hash, and phone number are all entered
- Make sure you clicked "Save Settings" in the web UI

### Not receiving verification code
- Check that your phone number includes the country code (e.g. +82)
- Verify you are logged into the Telegram app

### Auto response not working
- Check that the bot is running in the terminal
- "Bot is running..." message should be displayed
- Verify authentication is complete

### Web UI won't open
- Check if port 5000 is already in use
- Check if firewall is blocking localhost access

## Stopping the Bot

Press `Ctrl + C` to stop the bot.
