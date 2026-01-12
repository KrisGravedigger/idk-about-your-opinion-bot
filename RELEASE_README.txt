================================================================================
OPINION TRADING BOT - Standalone Version
================================================================================

Version: 0.3.0
Platform: Windows / Linux / macOS

Thank you for downloading Opinion Trading Bot!

This is a standalone executable version - no Python installation required.

================================================================================
QUICK START
================================================================================

1. EXTRACT ZIP
   - Extract this ZIP file to a folder of your choice
   - Example: C:\OpinionBot\ (Windows) or ~/OpinionBot/ (Linux/Mac)
   - Keep all files together in the same folder

2. FIRST RUN
   - Double-click OpinionBot.exe (Windows) or OpinionBot (Linux/Mac)
   - The bot will create necessary files automatically:
     • .env - For your API keys and credentials
     • bonus_markets.txt - Optional bonus markets list
     • bot_config.json - Bot configuration

3. CONFIGURE CREDENTIALS
   - Click the "🔐 Credentials" tab in the GUI
   - Enter your:
     • Opinion.trade API Key
     • Wallet Private Key (NEVER share this!)
     • Wallet Address
     • (Optional) Telegram Bot Token and Chat ID
   - Click "💾 Save Configuration"

4. CONFIGURE STRATEGY (Optional)
   - Visit other tabs to customize your trading strategy:
     • 💰 Capital - Position sizing
     • 📊 Markets - Market selection filters
     • 💱 Trading - Pricing strategy
     • 🛡️ Risk - Stop-loss and timeouts
     • 🔔 Monitoring - Logging and alerts

5. START TRADING
   - Click "▶ Start Bot" button
   - Monitor the real-time log viewer
   - Bot will automatically:
     → Find best markets
     → Place BUY orders
     → Monitor until filled
     → Place SELL orders
     → Track profit/loss
     → Repeat (if auto-reinvest enabled)

================================================================================
IMPORTANT FILES
================================================================================

DO NOT DELETE THESE FILES (created automatically):
  • .env - Your credentials (KEEP PRIVATE!)
  • state.json - Bot state (for resuming after restart)
  • pnl_stats.json - Trading statistics
  • bot_config.json - Your configuration
  • bonus_markets.txt - Bonus markets list

LOGS:
  • opinion_farming_bot.log - Detailed bot activity log

TEMPLATES (safe to delete):
  • .env.example - Template for credentials
  • README.md - Full documentation
  • README_RELEASE.txt - This file

================================================================================
UPDATING TO NEW VERSION
================================================================================

When the bot notifies you of a new version:

1. STOP THE BOT
   - Click "⏹ Stop Bot" button
   - Wait for bot to stop completely

2. DOWNLOAD NEW VERSION
   - Visit: https://github.com/YOUR_USERNAME/idk-about-your-opinion-bot/releases
   - Download the ZIP for your platform

3. EXTRACT TO SAME FOLDER
   - Extract new ZIP to the SAME folder as current installation
   - Overwrite files when asked

4. YOUR SETTINGS ARE PRESERVED
   The following files will NOT be overwritten:
   - .env (credentials)
   - state.json (bot state)
   - pnl_stats.json (statistics)
   - bot_config.json (configuration)
   - opinion_farming_bot.log (logs)

5. START BOT
   - Double-click OpinionBot.exe / OpinionBot
   - Your settings will be loaded automatically

The bot checks for updates automatically on startup and will notify you
when a new version is available.

================================================================================
TROUBLESHOOTING
================================================================================

Bot won't start:
  → Check .env file has valid API Key and Private Key
  → Click "🔧 Test Configuration" to diagnose issues
  → Check opinion_farming_bot.log for detailed errors

"Configuration errors found":
  → Go to 🔐 Credentials tab
  → Verify all fields are filled correctly
  → Click "💾 Save Configuration"
  → Click "🔧 Test Configuration"

"Insufficient balance":
  → Check your USDT balance on Opinion.trade
  → Reduce capital amount in 💰 Capital tab
  → Ensure you have at least 50 USDT for trading

"No markets found":
  → Opinion.trade may have no active markets at the moment
  → Check if filters are too restrictive (📊 Markets tab)
  → Try adjusting:
    - Time until close filters
    - Probability ranges
    - Orderbook balance filters
  → Wait a few minutes and try again

Telegram notifications not working:
  → Verify bot token and chat ID in 🔐 Credentials tab
  → Click "Test Telegram" button in 🔔 Monitoring tab
  → Make sure you've started a conversation with your bot on Telegram
  → Check internet connection

Order stuck pending:
  → This is normal - order is waiting for fill
  → Check if your order is competitive in the orderbook
  → Bot will auto-cancel after timeout (default: 8 hours)
  → You can stop bot with "⏹ Stop Bot" button

GUI is frozen:
  → The bot might be processing a long operation
  → Check the log viewer for activity
  → Wait a few seconds
  → If truly frozen, close and restart

Linux/macOS: "Permission denied":
  → Open terminal in the OpinionBot folder
  → Run: chmod +x OpinionBot
  → Then run: ./OpinionBot

================================================================================
SECURITY WARNING
================================================================================

⚠️  NEVER share your .env file or Private Key with anyone!
⚠️  Use a dedicated trading wallet (not your main wallet)
⚠️  Start with small amounts to test the bot
⚠️  Monitor the bot regularly - don't leave it unattended
⚠️  This is BETA software (v0.3) - use with caution

Your Private Key gives FULL ACCESS to your wallet. Anyone with access to
your .env file can drain your funds. Keep it secure!

================================================================================
BEST PRACTICES
================================================================================

1. TESTING
   - Start with minimum capital (50-100 USDT)
   - Run for 1-2 cycles to verify everything works
   - Monitor closely for first few hours
   - Check logs regularly

2. CAPITAL MANAGEMENT
   - Use percentage mode (80-95% of balance)
   - Keep minimum balance threshold reasonable
   - Don't risk more than you can afford to lose

3. MONITORING
   - Enable Telegram notifications for real-time alerts
   - Check bot status regularly
   - Review pnl_stats.json to track performance
   - Read opinion_farming_bot.log if issues occur

4. STRATEGY TUNING
   - Start with default settings
   - Adjust filters based on market conditions
   - Enable stop-loss protection (recommended)
   - Use bonus markets file for priority markets

5. UPDATES
   - Check for updates regularly
   - Read release notes before updating
   - Always backup .env file before major updates

================================================================================
FEATURES
================================================================================

✅ Fully Autonomous Trading
   - Complete trading cycle from market selection to position closing
   - No manual intervention required

✅ Intelligent Market Selection
   - Multi-factor scoring system
   - Bonus market support
   - YES/NO outcome trading

✅ Risk Management
   - Stop-loss protection (configurable)
   - Market filters (time, bias, probability)
   - Liquidity monitoring
   - Order timeouts

✅ Real-Time Monitoring
   - Live log viewer in GUI
   - Telegram notifications
   - P&L tracking
   - Trading statistics

✅ Easy Configuration
   - Visual GUI interface
   - Profile management
   - Import/export settings
   - Validation and testing tools

================================================================================
PERFORMANCE EXPECTATIONS
================================================================================

Realistic Expectations:
  - Win Rate: 50-70% (depends on market conditions)
  - Cycle Time: 1-8 hours per complete cycle
  - Returns: Variable based on market volatility
  - Airdrop Points: Maximized through smart market selection

This bot is designed to:
  ✓ Maximize airdrop points through strategic trading
  ✓ Generate modest profits from market making
  ✓ Manage risk through stop-loss and filters
  ✓ Operate autonomously with minimal supervision

This bot is NOT designed to:
  ✗ Guarantee profits (trading involves risk)
  ✗ Make you rich overnight
  ✗ Replace professional trading
  ✗ Work in all market conditions

================================================================================
SUPPORT & DOCUMENTATION
================================================================================

Full Documentation:
  - README.md (included in this distribution)
  - Online: https://github.com/YOUR_USERNAME/idk-about-your-opinion-bot

Report Issues:
  - GitHub Issues: https://github.com/YOUR_USERNAME/idk-about-your-opinion-bot/issues
  - Include:
    • Version number (see GUI title bar)
    • Error message
    • Relevant log excerpt
    • Steps to reproduce

Get Updates:
  - Releases: https://github.com/YOUR_USERNAME/idk-about-your-opinion-bot/releases
  - Bot checks automatically on startup

================================================================================
LICENSE
================================================================================

MIT License - See LICENSE file for details

================================================================================
DISCLAIMER
================================================================================

⚠️  IMPORTANT - READ CAREFULLY

This bot is provided for EDUCATIONAL PURPOSES ONLY. Trading prediction
markets involves substantial risk of loss.

VERSION 0.3 IS BETA SOFTWARE:
  - New features have not been extensively tested
  - Bugs may exist that could result in financial losses
  - Use with extreme caution
  - Monitor closely and be prepared to intervene manually

RISKS:
  - You can lose all capital deployed
  - Markets can be volatile and unpredictable
  - Bugs in the code could result in losses
  - API or network issues could cause problems
  - Stop-loss is NOT foolproof and may fail
  - No guarantees of profitability

YOU ARE RESPONSIBLE FOR:
  - Testing thoroughly with small amounts
  - Understanding the bot before running it
  - Monitoring the bot regularly
  - Managing your own risk
  - Any financial losses incurred

THE DEVELOPERS:
  - Provide no warranties or guarantees
  - Are not responsible for any losses
  - Do not provide financial advice
  - Recommend professional advice before trading

By using this software, you acknowledge and accept these risks.

================================================================================

Happy Trading! 🤖

Remember: Start small, test thoroughly, monitor closely, and never invest
more than you can afford to lose.

================================================================================
