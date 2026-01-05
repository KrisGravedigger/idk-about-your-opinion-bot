# Opinion Trading Bot 🤖

**Version 0.3 (Beta)**

**Autonomous trading bot for Opinion.trade prediction markets on BNB Chain**

A sophisticated liquidity provision bot designed to maximize airdrop points while generating trading profits through automated market-making strategies.

> ⚠️ **BETA SOFTWARE**: Version 0.3 introduces significant new features (Telegram notifications, persistent P&L statistics, enhanced market filters) that have not been extensively tested in production. **Use with caution** and start with small amounts. Monitor the bot closely and report any issues.

---

## 📋 Table of Contents

- [What's New in 0.3](#-whats-new-in-03)
- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Telegram Notifications](#-telegram-notifications)
- [Running the Bot](#-running-the-bot)
- [How It Works](#-how-it-works)
- [Module Overview](#-module-overview)
- [Safety Features](#-safety-features)
- [Troubleshooting](#-troubleshooting)
- [Development](#-development)
- [License & Disclaimer](#-license--disclaimer)

---

## 🎉 What's New in 0.3

### 🆕 Major Features

**1. Telegram Notifications** 📱
- Real-time notifications for all important bot events
- Bot start/stop with comprehensive statistics
- State change alerts (BUY_PLACED, SELL_PLACED)
- Stop-loss trigger notifications
- Configurable heartbeat updates (default: every hour)
- Complete setup guide in [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)

**2. Persistent P&L Statistics** 📊
- Separate `pnl_stats.json` file for statistics persistence
- Statistics survive even if `state.json` is deleted
- Auto-display on bot startup
- Enhanced tracking: best/worst trades, average win/loss
- Historical performance preserved across sessions

**3. Enhanced Risk Management** 🛡️
- **Stop-loss protection** - Automatic position closure at configurable loss threshold
- **Market expiration filters** - Skip markets closing too soon or too far in the future
- **Orderbook bias filters** - Avoid heavily imbalanced markets
- **Improved market selection** - Better filters for market quality

**4. YES/NO Market Support** 🎯
- Full support for both YES and NO outcome trading
- Automatic outcome selection based on market conditions
- Probability-based filtering for both sides

### ⚡ Improvements
- More robust state recovery after interruptions
- Better error handling and logging
- Enhanced position tracking and P&L calculation
- Improved market scoring algorithms

---

## ✨ Features

### Core Trading Engine
- **Fully Autonomous Operation** - Complete trading cycle from market selection to position closing
- **State Machine Architecture** - 8-stage state machine with persistence across restarts
- **Intelligent Market Selection** - Multi-factor scoring system with bonus market support
- **YES/NO Market Support** - Trades both YES and NO outcomes based on market conditions
- **Advanced Pricing Strategy** - Threshold-based market making with safety checks
- **Smart Order Monitoring** - Detects fills, competition, and market deterioration

### Risk Management
- **Capital Management** - Fixed or percentage-based position sizing
- **Stop-Loss Protection** ⭐ NEW - Automatic position closure when losses exceed threshold (-10% default)
- **Market Filters** ⭐ NEW - Skip markets closing too soon/late or heavily biased
- **Liquidity Monitoring** - Detects and responds to orderbook deterioration
- **Order Timeouts** - Automatic cancellation after configurable time periods
- **Balance Safety Checks** - Prevents over-trading when capital is low

### Analytics & Notifications
- **Persistent P&L Statistics** ⭐ NEW - Separate file preserves stats across sessions
- **Telegram Notifications** ⭐ NEW - Real-time alerts for all important events
- **P&L Calculation** - Precise profit/loss tracking using Decimal arithmetic
- **Trade Statistics** - Win rate, total P&L, consecutive losses, best/worst trades
- **Session Summaries** - Comprehensive performance reports on startup and shutdown
- **State Persistence** - Resume interrupted trading cycles seamlessly

---

## 🏗️ Architecture

### Project Structure

```
opinion_trading_bot/
├── core/                          # Core business logic
│   ├── autonomous_bot.py          # Main orchestrator (state machine)
│   ├── capital_manager.py         # Position sizing & balance checks
│   └── state_manager.py           # State persistence & validation
│
├── monitoring/                    # Order & market monitoring
│   ├── buy_monitor.py             # BUY order fill monitoring
│   ├── sell_monitor.py            # SELL order fill & stop-loss monitoring
│   └── liquidity_checker.py      # Orderbook liquidity analysis
│
├── strategies/                    # Trading strategies
│   └── pricing.py                 # Threshold-based pricing strategy
│
├── api_client.py                  # Opinion.trade API wrapper
├── market_scanner.py              # Market discovery & ranking
├── order_manager.py               # Order placement & management
├── position_tracker.py            # P&L calculation & tracking
├── pnl_statistics.py              # ⭐ NEW - Persistent P&L stats manager
├── telegram_notifications.py      # ⭐ NEW - Telegram notification service
├── scoring.py                     # Market scoring algorithms
├── utils.py                       # Helper functions
├── logger_config.py               # Logging configuration
├── config.py                      # Configuration parameters
│
├── autonomous_bot_main.py         # Entry point
├── state.json                     # Bot state (auto-generated)
├── pnl_stats.json                 # ⭐ NEW - P&L statistics (auto-generated)
├── bonus_markets.txt              # Bonus market IDs
├── .env                           # Credentials (create from .env.example)
└── TELEGRAM_SETUP.md              # ⭐ NEW - Telegram setup guide
```

### State Machine

```
IDLE → SCANNING → BUY_PLACED → BUY_MONITORING → BUY_FILLED →
SELL_PLACED → SELL_MONITORING → COMPLETED → IDLE (repeat)
```

**Stage Descriptions:**
- `IDLE`: Ready to start new cycle
- `SCANNING`: Finding and ranking markets (YES/NO outcomes)
- `BUY_PLACED`: BUY order submitted, transitioning to monitoring
- `BUY_MONITORING`: Monitoring BUY order for fills/competition
- `BUY_FILLED`: BUY completed, preparing SELL order
- `SELL_PLACED`: SELL order submitted, transitioning to monitoring
- `SELL_MONITORING`: Monitoring SELL order for fills/stop-loss
- `COMPLETED`: Trade finished, calculating P&L

---

## 🚀 Quick Start

```bash
# 1. Clone repository
git clone <repository-url>
cd opinion_trading_bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env with your API_KEY, PRIVATE_KEY, MULTI_SIG_ADDRESS

# 4. (Optional) Configure Telegram notifications
# See TELEGRAM_SETUP.md for detailed instructions
# Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env

# 5. (Optional) Add bonus markets
# Edit bonus_markets.txt with market IDs (one per line)

# 6. Adjust configuration
# Edit config.py to set capital, strategy parameters, etc.

# 7. Run the bot
python autonomous_bot_main.py

# Optional flags:
python autonomous_bot_main.py --max-cycles 5  # Run for 5 cycles then stop
python autonomous_bot_main.py --reset-state   # Start fresh (clear previous state)
```

---

## 📦 Installation

### Requirements

- **Python 3.10+**
- **BNB Chain wallet** with:
  - USDT for trading (minimum 20 USDT recommended)
  - Small amount of BNB for gas fees (0.01 BNB)
- **Opinion.trade API key**
- **(Optional) Telegram account** for notifications

### Setup Steps

1. **Create virtual environment** (recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate  # Windows
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials**
   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```env
   API_KEY=your_opinion_trade_api_key
   PRIVATE_KEY=0xYourWalletPrivateKey
   MULTI_SIG_ADDRESS=0xYourWalletAddress

   # Optional: Telegram notifications
   TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
   TELEGRAM_CHAT_ID=your_chat_id
   ```

4. **Configure bot behavior**

   Edit `config.py` to adjust:
   - Capital allocation (`CAPITAL_MODE`, `CAPITAL_AMOUNT_USDT`, `CAPITAL_PERCENTAGE`)
   - Pricing strategy thresholds
   - Stop-loss parameters
   - Market filters (expiration, bias)
   - Monitoring intervals
   - Telegram heartbeat interval
   - Risk management settings

---

## ⚙️ Configuration

### Essential Parameters (`config.py`)

#### Capital Management

```python
# Capital mode: 'fixed' or 'percentage'
CAPITAL_MODE = 'percentage'

# Fixed mode: use this exact amount per position
CAPITAL_AMOUNT_USDT = 20.0

# Percentage mode: use this % of current balance
CAPITAL_PERCENTAGE = 90.0

# Safety thresholds
MIN_BALANCE_TO_CONTINUE_USDT = 50.0
MIN_POSITION_SIZE_USDT = 50.0
```

#### Market Filters (NEW in 0.3)

```python
# Time-based filters (hours)
MIN_HOURS_UNTIL_CLOSE = 30    # Skip markets closing too soon
MAX_HOURS_UNTIL_CLOSE = None  # Skip markets closing too far out

# Orderbook balance filter
# (min_percentage, max_percentage) for BID side volume
ORDERBOOK_BALANCE_RANGE = (45, 80)  # Skip if <45% or >80% bids

# Outcome probability filters
OUTCOME_MIN_PROBABILITY = 0.30  # Skip if implied prob < 30%
OUTCOME_MAX_PROBABILITY = 0.84  # Skip if implied prob > 84%
```

#### Pricing Strategy

```python
# Spread thresholds (in dollars)
SPREAD_THRESHOLD_1 = 0.20  # Tiny spreads: ≤$0.20
SPREAD_THRESHOLD_2 = 0.50  # Small spreads: $0.21-$0.50
SPREAD_THRESHOLD_3 = 1.00  # Medium spreads: $0.51-$1.00
                           # Wide spreads: >$1.00

# Improvement amounts for each threshold
IMPROVEMENT_TINY = 0.00    # Join queue (no improvement)
IMPROVEMENT_SMALL = 0.10   # $0.10 better
IMPROVEMENT_MEDIUM = 0.20  # $0.20 better
IMPROVEMENT_WIDE = 0.30    # $0.30 better
```

#### Stop-Loss Protection (NEW in 0.3)

```python
ENABLE_STOP_LOSS = True
STOP_LOSS_TRIGGER_PERCENT = -10.0  # Trigger at -10% loss
STOP_LOSS_AGGRESSIVE_OFFSET = 0.001  # Place aggressive limit
```

#### Telegram Notifications (NEW in 0.3)

```python
# Heartbeat interval (hours) - send periodic status updates
# Set to 0 to disable heartbeat notifications
TELEGRAM_HEARTBEAT_INTERVAL_HOURS = 1.0
```

#### Liquidity Monitoring

```python
LIQUIDITY_AUTO_CANCEL = True
LIQUIDITY_BID_DROP_THRESHOLD = 25.0  # Cancel if bid drops >25%
LIQUIDITY_SPREAD_THRESHOLD = 15.0    # Cancel if spread >15%
```

### Scoring Profiles

Define market selection strategies in `config.py`:

```python
SCORING_PROFILES = {
    'production_farming': {
        'weights': {
            'price_balance': 0.45,      # 50/50 bid/ask balance
            'hourglass_advanced': 0.25,  # Orderbook shape
            'spread': 0.20,              # Wide spreads
            'volume_24h': 0.10,          # High volume bonus
        },
        'bonus_multiplier': 1.5,
        'invert_spread': False,  # Larger = better
    },
    'test_quick_fill': {
        'weights': {
            'spread': 1.0,  # Only spread matters
        },
        'bonus_multiplier': 1.0,
        'invert_spread': True,  # Smaller = better (fast fills)
    },
}

DEFAULT_SCORING_PROFILE = 'production_farming'
```

---

## 📱 Telegram Notifications

### Setup

See **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)** for complete step-by-step instructions.

**Quick setup:**
1. Message `@BotFather` on Telegram → create bot → copy token
2. Message `@userinfobot` on Telegram → copy your Chat ID
3. Add to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

### Notification Types

**Bot Start** 🚀
- Current P&L statistics
- Available capital and balance
- Capital mode and scoring profile
- Stop-loss status

**Bot Stop** ⛔
- Final P&L statistics
- Last 20 log lines before shutdown
- Timestamp

**State Changes** 📍
- BUY order placed
- SELL order placed
- Market details and prices

**Stop-Loss** 🚨
- Trigger notification
- Current loss percentage
- Price comparison

**Heartbeat** 💓
- Periodic status updates (default: every hour)
- Current state and market info
- Balance and position value
- Sent silently (no notification sound)

### Testing

Test your Telegram connection:
```bash
python telegram_notifications.py
```

You should receive several test messages on Telegram.

---

## 🎮 Running the Bot

### Standard Operation

```bash
python autonomous_bot_main.py
```

The bot will:
1. Display P&L statistics from previous sessions
2. Send Telegram notification (if configured)
3. Load/initialize state
4. Find best market (YES or NO outcome)
5. Place BUY order
6. Monitor until filled
7. Place SELL order
8. Monitor until filled (with stop-loss protection)
9. Calculate P&L and update statistics
10. Repeat (if `AUTO_REINVEST=True`)

### Command Line Options

```bash
# Run for specific number of cycles
python autonomous_bot_main.py --max-cycles 5

# Clear previous state and start fresh
python autonomous_bot_main.py --reset-state

# Show help
python autonomous_bot_main.py --help
```

### Interrupting the Bot

- Press `Ctrl+C` to stop gracefully
- Bot saves state before exiting
- Sends Telegram stop notification (if configured)
- Resume later by running again (state persists)

### Monitoring Output

The bot provides real-time logging with emojis:

| Symbol | Meaning |
|--------|---------|
| ✅ | Success |
| ❌ | Error |
| ⚠️ | Warning |
| 🔄 | Processing |
| 💰 | Money/P&L |
| 📊 | Data/Stats |
| 🌟 | Bonus market |
| 🛑 | Stop-loss |
| 📱 | Telegram notification |
| 💓 | Heartbeat |

---

## 🔧 How It Works

### Market Selection

1. **Fetch Active Markets** - Query all markets from API
2. **Generate Outcomes** - Create YES/NO outcome candidates from each market
3. **Apply Filters** - Remove outcomes that don't meet criteria:
   - Minimum orderbook depth
   - Time until close constraints (NEW in 0.3)
   - Orderbook balance requirements (NEW in 0.3)
   - Probability ranges (NEW in 0.3)
   - Minimum order book orders
4. **Score Outcomes** - Calculate score based on:
   - Spread percentage
   - Price balance (50/50 bid/ask)
   - Orderbook shape (hourglass pattern)
   - 24h volume
   - Bonus multiplier (if in bonus_markets.txt)
5. **Select Best** - Choose highest scoring outcome (YES or NO)

### Order Execution

**BUY Orders:**
```
1. Get current orderbook
2. Calculate spread (ask - bid)
3. Determine improvement based on spread size:
   - Tiny spread (≤$0.20) → bid + $0.00 (join queue)
   - Small spread ($0.21-$0.50) → bid + $0.10
   - Medium spread ($0.51-$1.00) → bid + $0.20
   - Wide spread (>$1.00) → bid + $0.30
4. Apply safety checks (don't cross ask)
5. Place limit order
6. Send Telegram notification
```

**SELL Orders:**
```
1. Get current orderbook
2. Calculate spread
3. Determine improvement (same thresholds, subtract from ask)
4. Apply safety checks (don't cross bid)
5. Place limit order
6. Send Telegram notification
```

### Monitoring & Risk Management

**BUY Monitoring:**
- Checks order status every 9 seconds
- Monitors orderbook liquidity
- Cancels if:
  - Bid drops >25% from initial
  - Spread widens >15%
  - Timeout reached (8 hours default)

**SELL Monitoring (with Stop-Loss):**
- Checks order status every 9 seconds
- Calculates unrealized P&L continuously
- **Triggers stop-loss if:**
  - Loss exceeds threshold (-10% default)
  - Places aggressive limit order to exit
  - Sends Telegram notification
- Monitors liquidity deterioration
- Cancels if timeout reached (8 hours default)

### P&L Calculation & Statistics

```python
buy_cost = amount_usdt (what we spent)
sell_proceeds = filled_tokens × sell_price (what we received)
pnl = sell_proceeds - buy_cost
pnl_percent = (pnl / buy_cost) × 100
```

Uses `Decimal` arithmetic for precision.

**Statistics tracked (NEW in 0.3):**
- Total trades, wins, losses
- Total P&L in USDT
- Win rate percentage
- Best/worst trade
- Average win/loss amounts
- Consecutive losses

Statistics are saved to `pnl_stats.json` and persist even if `state.json` is deleted.

---

## 📚 Module Overview

### Core Modules

**`core/autonomous_bot.py`**
- Main orchestrator implementing state machine
- Coordinates all modules
- Handles state transitions
- Manages trading cycle
- **NEW:** Telegram notification integration
- **NEW:** Heartbeat timing and sending

**`core/capital_manager.py`**
- Calculates position sizes
- Queries USDT balance
- Validates against platform constraints
- Warns if position too small for airdrop points

**`core/state_manager.py`**
- Loads/saves state.json
- Initializes fresh state
- Validates state structure
- Migrates old formats
- Resets positions between cycles

### New Modules (0.3)

**`pnl_statistics.py`** ⭐ NEW
- Manages persistent P&L statistics in separate file
- Tracks best/worst trades, averages
- Survives state.json deletions
- Auto-displays on startup

**`telegram_notifications.py`** ⭐ NEW
- Telegram notification service
- Sends formatted messages for all events
- HTML formatting support
- Error handling for network issues

### Monitoring Modules

**`monitoring/buy_monitor.py`**
- Monitors BUY orders until filled
- Checks liquidity conditions
- Handles timeouts
- Returns structured results

**`monitoring/sell_monitor.py`**
- Monitors SELL orders until filled
- Calculates unrealized P&L
- **Triggers stop-loss if threshold exceeded**
- Monitors liquidity deterioration

**`monitoring/liquidity_checker.py`**
- Compares current vs initial orderbook
- Calculates bid drop percentage
- Calculates spread percentage
- Returns deterioration analysis

### Strategy Modules

**`strategies/pricing.py`**
- Threshold-based pricing strategy
- Calculates BUY/SELL prices
- Applies safety margins
- Prevents spread crossing

### Support Modules

**`api_client.py`**
- Opinion.trade API wrapper
- Handles authentication
- Provides convenience methods
- Error handling

**`market_scanner.py`**
- Fetches all active markets
- **Generates YES/NO outcomes**
- Applies filters (time, bias, probability)
- Calculates scores
- Returns ranked list

**`order_manager.py`**
- Places BUY/SELL orders
- Cancels orders
- Fetches order status
- Handles order-related operations

**`position_tracker.py`**
- Calculates P&L using Decimal arithmetic
- Tracks trade history
- Provides session summaries
- Win rate calculations

**`scoring.py`**
- Market scoring algorithms
- Price balance metric
- Hourglass pattern detection
- Volume/liquidity scoring

**`utils.py`**
- Helper functions
- Formatting utilities
- Safe type conversions
- Timestamp generation

**`logger_config.py`**
- Centralized logging setup
- Console + file output
- Color coding
- Structured logging helpers

---

## 🛡️ Safety Features

### Capital Protection

- **Minimum Balance Check** - Exits if balance < threshold
- **Position Size Validation** - Ensures orders meet platform minimums
- **Capital Allocation** - Prevents over-leveraging

### Order Safety

- **Spread Crossing Prevention** - Orders never cross spread (remain makers)
- **Safety Margins** - Minimum distance from opposite side
- **Price Validation** - Checks prices before submission

### Risk Management (Enhanced in 0.3)

- **Stop-Loss Protection** ⭐ - Automatic position closure at loss threshold (-10% default)
- **Market Filters** ⭐ - Skip markets closing too soon/late (configurable)
- **Bias Filters** ⭐ - Avoid heavily imbalanced orderbooks (45-80% range)
- **Probability Filters** ⭐ - Skip outcomes with extreme probabilities (30-84% range)
- **Liquidity Monitoring** - Cancels orders in deteriorating conditions
- **Order Timeouts** - Prevents indefinite waiting
- **State Persistence** - Resume after crashes/interruptions

### Operational Safety

- **Graceful Shutdown** - Ctrl+C saves state before exit
- **Error Handling** - Comprehensive try/catch blocks
- **Logging** - Full audit trail of all operations
- **Validation** - Config validation at startup
- **Telegram Alerts** ⭐ NEW - Real-time notifications of important events

---

## 🔍 Troubleshooting

### Common Issues

**"Configuration errors found"**
- Check `.env` file exists and has all required values
- Verify API_KEY is valid
- Ensure PRIVATE_KEY is 64 hex characters

**"Insufficient balance"**
- Check USDT balance: `client.get_usdt_balance()`
- Reduce `CAPITAL_AMOUNT_USDT` or `CAPITAL_PERCENTAGE`
- Ensure `MIN_BALANCE_TO_CONTINUE_USDT` is appropriate

**"No markets found"**
- Opinion.trade may have no active markets
- Check if filters are too restrictive (time, bias, probability)
- Check internet connection
- Try again later

**Order stuck in "pending"**
- Normal - order waiting for fill
- Check if you're competitive in orderbook
- Wait or cancel with Ctrl+C

**"Failed to place order"**
- Insufficient USDT balance
- Insufficient BNB for gas (for some operations)
- Invalid API key
- Network issues

**Telegram notifications not working**
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
- Check you've started conversation with bot on Telegram
- Run test: `python telegram_notifications.py`
- See [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md) for detailed troubleshooting

### Debug Mode

Enable detailed logging:

```python
# In config.py
LOG_LEVEL = "DEBUG"
```

Check `opinion_farming_bot.log` for full details.

### State Issues

If state.json becomes corrupted:

```bash
python autonomous_bot_main.py --reset-state
```

Or manually delete `state.json`.

**Note:** P&L statistics in `pnl_stats.json` are preserved separately.

---

## 👨‍💻 Development

### Project Structure

The codebase follows modular architecture with clear separation of concerns:

- **Core** - Business logic and orchestration
- **Monitoring** - Order and market monitoring
- **Strategies** - Trading strategies (pricing, etc.)
- **Support** - Utilities, logging, API client
- **Notifications** - Telegram integration (NEW in 0.3)

### Adding New Features

1. **New Strategy** - Add to `strategies/`
2. **New Monitor** - Add to `monitoring/`
3. **New Metric** - Add to `scoring.py`
4. **New State** - Update `state_manager.py` and migration logic
5. **New Notification** - Add to `telegram_notifications.py`

### Testing

⚠️ **Version 0.3 is BETA** - New features have limited production testing.

Always:
1. Test with small amounts first
2. Use `--max-cycles 1` for single-cycle testing
3. Monitor logs carefully
4. Verify state.json and pnl_stats.json after each cycle
5. Test Telegram notifications before relying on them

### Code Quality

- **Type Hints** - Used throughout for clarity
- **Docstrings** - All public functions documented
- **Comments** - Non-obvious logic explained
- **Logging** - Comprehensive logging at all levels

---

## 📄 License & Disclaimer

### Disclaimer

⚠️ **IMPORTANT - READ CAREFULLY**

This bot is provided for **educational purposes only**. Trading prediction markets involves substantial risk of loss.

**VERSION 0.3 IS BETA SOFTWARE:**
- New features (Telegram, persistent stats, enhanced filters) have not been extensively tested
- Bugs may exist that could result in financial losses
- **Use with extreme caution** and start with minimal capital
- Monitor the bot closely and be prepared to intervene manually
- Report any issues immediately

**RISKS:**
- You can lose all capital deployed
- Markets can be volatile and unpredictable
- Bugs in the code could result in losses
- API or network issues could cause problems
- Stop-loss is NOT foolproof and may fail
- No guarantees of profitability

**YOU ARE RESPONSIBLE FOR:**
- Testing thoroughly with small amounts
- Understanding the code before running it
- Monitoring the bot regularly
- Managing your own risk
- Any financial losses incurred

**THE DEVELOPERS:**
- Provide no warranties or guarantees
- Are not responsible for any losses
- Do not provide financial advice
- Recommend professional advice before trading

### License

MIT License - See LICENSE file for details

---

## 🤝 Support & Community

### Getting Help

1. Check this README thoroughly
2. Review `opinion_farming_bot.log`
3. Check [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md) for Telegram issues
4. Search existing GitHub issues
5. Open new issue with:
   - Version number (0.3)
   - Full error message
   - Relevant log excerpt
   - Configuration (without credentials!)
   - Steps to reproduce

### Contributing

Contributions welcome! Please:
1. Fork repository
2. Create feature branch
3. Add tests if applicable
4. Submit pull request

---

## 📊 Performance Expectations

### Realistic Expectations

- **Win Rate**: 50-70% (depends on market conditions)
- **Average P&L**: Variable, depends on market volatility
- **Cycle Time**: 1-8 hours per complete cycle (with timeouts)
- **Airdrop Points**: Maximized through strategic market selection

### Factors Affecting Performance

- Market volatility
- Competition from other traders
- Spread availability
- Capital allocated
- Configuration parameters
- Stop-loss threshold
- Market filters (may reduce opportunities)

---

## 🔐 Security Best Practices

### Credential Management

- ✅ **DO** use `.env` file for credentials
- ✅ **DO** use dedicated trading wallet
- ✅ **DO** start with small amounts (especially in 0.3 beta)
- ✅ **DO** keep backup of private key offline
- ✅ **DO** secure your Telegram bot token
- ❌ **DON'T** commit `.env` to Git
- ❌ **DON'T** share private key or bot token
- ❌ **DON'T** use main wallet
- ❌ **DON'T** leave large amounts unmonitored

### Operational Security

- Keep software updated
- Use secure network connections
- Monitor bot regularly (use Telegram notifications!)
- Review logs periodically
- Set appropriate stop-loss thresholds
- Test Telegram alerts before relying on them

---

## 📈 Roadmap

### Completed ✅

- [x] ~~Telegram notifications~~ (v0.3)
- [x] ~~Persistent P&L statistics~~ (v0.3)
- [x] ~~Stop-loss protection~~ (v0.3)
- [x] ~~Market expiration filters~~ (v0.3)
- [x] ~~YES/NO market support~~ (v0.3)

### Planned Features

- [ ] CSV transaction logging for analysis
- [ ] Multi-market support (parallel positions)
- [ ] Web dashboard
- [ ] Backtesting framework
- [ ] Advanced strategies (e.g., momentum, mean reversion)
- [ ] Mobile app integration

### Known Limitations

- Single position at a time
- Manual configuration updates
- Limited historical data analysis
- No GUI interface
- Beta stability (v0.3)

---

## 📞 Contact

For issues, questions, or contributions:
- GitHub Issues: [Repository Issues Page]
- Documentation: This README + [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)
- Code: Fully commented and documented

---

## 📝 Version History

### Version 0.3 (Current - Beta)
- Added Telegram notifications
- Added persistent P&L statistics
- Enhanced market filters (time, bias, probability)
- Stop-loss protection
- YES/NO market support
- Improved state recovery

### Version 0.2
- Basic autonomous trading
- State machine implementation
- Market scoring and selection
- Order monitoring
- P&L tracking

---

**Happy Trading! 🌾**

Remember: **Version 0.3 is BETA**. Start small, test thoroughly, monitor closely, and never invest more than you can afford to lose.
