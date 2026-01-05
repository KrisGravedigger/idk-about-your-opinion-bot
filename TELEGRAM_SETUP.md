# Telegram Notifications Setup Guide

This guide will help you set up Telegram notifications for the Opinion Farming Bot using BotFather.

## Prerequisites

- Telegram account
- Telegram app (mobile or desktop)

## Step 1: Create a Telegram Bot

1. **Open Telegram** and search for `@BotFather`
   - BotFather is Telegram's official bot for creating and managing bots
   - Official username: `@BotFather`

2. **Start a conversation** with BotFather
   - Click "Start" or send `/start`

3. **Create a new bot**
   - Send the command: `/newbot`

4. **Choose a name for your bot**
   - BotFather will ask: "Alright, a new bot. How are we going to call it?"
   - Enter a display name, e.g., `Opinion Farming Bot`
   - This name will be shown in contact details and elsewhere

5. **Choose a username for your bot**
   - BotFather will ask: "Good. Now let's choose a username for your bot."
   - Username must end in `bot` (e.g., `opinion_farming_bot` or `MyOpinionBot`)
   - Username must be unique across all of Telegram
   - Example: `my_opinion_farming_bot`

6. **Save your bot token**
   - BotFather will respond with a message containing your bot token
   - Example token: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
   - ⚠️ **Keep this token secret!** Anyone with this token can control your bot
   - Copy this token - you'll need it in Step 3

## Step 2: Get Your Chat ID

There are two methods to get your Chat ID:

### Method A: Using @userinfobot (Recommended)

1. **Search for** `@userinfobot` in Telegram

2. **Start a conversation**
   - Click "Start" or send any message

3. **Copy your Chat ID**
   - The bot will reply with your user information
   - Look for the line that says `Id: 123456789`
   - Copy this number (your Chat ID)
   - Example: `123456789`

### Method B: Using @raw_data_bot (Alternative)

1. **Search for** `@raw_data_bot` in Telegram

2. **Start a conversation**
   - Click "Start" or send any message

3. **Find your Chat ID in the JSON response**
   - Look for `"id": 123456789` in the response
   - Copy this number

## Step 3: Configure Your Bot

1. **Open your `.env` file** in the bot directory
   - If you don't have a `.env` file, copy `.env.example`:
     ```bash
     cp .env.example .env
     ```

2. **Add your credentials** to the `.env` file:
   ```bash
   # Telegram Notifications
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHAT_ID=123456789
   ```

   Replace:
   - `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` with your actual bot token from Step 1
   - `123456789` with your actual Chat ID from Step 2

3. **Save the file**

## Step 4: Start Your Bot

1. **Find your bot** in Telegram
   - Search for the username you created (e.g., `@my_opinion_farming_bot`)

2. **Start the bot**
   - Click "Start" or send `/start`
   - This allows your bot to send you messages

## Step 5: Test the Connection

1. **Run the Telegram notification test script**:
   ```bash
   python telegram_notifications.py
   ```

2. **Check your Telegram**
   - You should receive several test messages from your bot
   - If you receive the messages, the setup is complete! ✅

3. **Troubleshooting** (if you don't receive messages):
   - Double-check your bot token in `.env`
   - Double-check your Chat ID in `.env`
   - Make sure you started a conversation with your bot in Telegram (Step 4.2)
   - Check that there are no spaces or quotes around the values in `.env`
   - Verify your internet connection

## Step 6: Configure Notification Preferences

You can customize notification settings in `config.py`:

```python
# Heartbeat interval (hours) - send periodic status updates
# Set to 0 to disable heartbeat notifications
TELEGRAM_HEARTBEAT_INTERVAL_HOURS = 1.0
```

Adjust this value to control how often you receive heartbeat updates:
- `0.5` = every 30 minutes
- `1.0` = every hour (default)
- `2.0` = every 2 hours
- `0` = disabled (no heartbeat notifications)

## What Notifications Will You Receive?

Once configured, you'll receive notifications for:

1. **Bot Started** 🚀
   - Current P&L statistics
   - Available capital
   - Capital mode (fixed/percentage)
   - Scoring profile
   - Stop-loss status

2. **Bot Stopped** ⛔
   - Final P&L statistics
   - Last 20 log lines
   - Timestamp

3. **State Changes** 📍
   - When BUY order is placed
   - When SELL order is placed
   - Market details and order information

4. **Stop-Loss Triggered** 🚨
   - Market information
   - Current loss percentage
   - Price details

5. **Heartbeat** 💓
   - Current bot status
   - Balance and position value
   - Market spread (if in position)
   - Sent silently (no notification sound)

## Security Best Practices

⚠️ **Important Security Notes:**

1. **Never share your bot token** - Anyone with this token can control your bot
2. **Never commit `.env` to git** - The `.gitignore` file should already exclude it
3. **Keep your Chat ID private** - While less critical, it's still personal information
4. **Revoke compromised tokens** - If your token is leaked:
   - Message BotFather: `/mybots`
   - Select your bot
   - API Token → Revoke current token
   - Update your `.env` with the new token

## Advanced: Using with Groups

If you want to send notifications to a Telegram group instead of a direct message:

1. **Create a Telegram group**
2. **Add your bot to the group** (as an admin if possible)
3. **Get the group Chat ID**:
   - Add `@raw_data_bot` to the group
   - Send a message in the group
   - Look for `"id": -123456789` (negative number for groups)
   - Use this negative number as your `TELEGRAM_CHAT_ID`

## Troubleshooting

### "Unauthorized" Error
- Check that your bot token is correct
- Make sure there are no extra spaces in the token

### "Chat not found" Error
- Verify your Chat ID is correct
- Ensure you've started a conversation with your bot first
- For groups, make sure the bot is a member

### No Messages Received
- Check your spam/archived chats in Telegram
- Verify the bot is running and configured correctly
- Run the test script to verify connection

### Messages Too Frequent
- Increase `TELEGRAM_HEARTBEAT_INTERVAL_HOURS` in `config.py`
- Or set to `0` to disable heartbeat

## Support

If you encounter issues:

1. Check the bot logs in `opinion_farming_bot.log`
2. Verify your credentials in `.env`
3. Run the test script: `python telegram_notifications.py`
4. Check the project README for additional troubleshooting

---

**Congratulations!** 🎉 Your Telegram notifications are now set up. Your bot will keep you informed about all important trading events.
