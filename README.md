# Opinion Trading Bot 🤖

**Version 1.1.0 - The Repricing Update**

**Autonomous trading bot for Opinion.trade prediction markets on BNB Chain**

---

## 📖 tl;dr

**TL;DR:** Autonomous trading bot for Opinion.trade prediction markets (BNB Chain). Maximizes airdrop points through intelligent market-making with risk controls.
**Top 5 features:**
  (1) Fully autonomous trading cycle, 
  (2) Stop-loss & sell order repricing, 
  (3) Telegram notifications, 
  (4) One-click GUI, 
  (5) Persistent P&L statistics.

---

## 🚀 Quick Start (10 steps, ~5 minutes)

1. **Prepare environment** - VPS or VPN outside banned jurisdictions ([terms](https://app.opinion.trade/terms))
2. **Request API key** - [Google Form](https://docs.google.com/forms/d/1h7gp8UffZeXzYQ-lv4jcou9PoRNOqMAQhyW4IwZDnII/viewform?edit_requested=true)
3. **Create dedicated wallet** - Fund with BNB (gas) + USDT (trading), connect to opinion.trade
4. **Transfer USDT** - From wallet to opinion.trade exchange (Opinion page)
5. **Download release** - [Latest version](https://github.com/KrisGravedigger/idk-about-your-opinion-bot/releases/latest)
6. **Extract ZIP** - Windows: `OpinionBot_Windows.zip` | Linux/macOS: appropriate file
7. **Run executable** - `OpinionBot.exe` (Windows) or `OpinionBot` (Linux/macOS)
8. **Fill in credentials** - API keys (Opinion + Telegram), parameters (read tooltips if unsure)
9. **Save settings** - "Save Configuration" button
10. **Start!** - "▶️ Start Bot" button → Watch logs or sleep peacefully (Telegram notifications)

**If problems occur:** Stop bot → Cancel/sell position manually on opinion.trade

---

## 📋 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Configuration](#️-configuration)
- [GUI](#️-gui-configuration-tool)
- [Telegram](#-telegram-notifications)
- [How It Works](#-how-it-works)
- [Safety](#️-safety-features)
- [Troubleshooting](#-troubleshooting)
- [License](#-license--disclaimer)

---

## ✨ Features

### Trading Engine
- **Autonomous cycle** - Scanning → BUY → SELL → P&L → Repeat
- **YES/NO markets** - Trades both sides of markets
- **Intelligent scoring** - Multi-factor market selection with bonuses
- **Sell order repricing** ⭐ **v1.1** - 3 modes (best/second_best/liquidity_percent), dynamic return to higher price
- **Stop-loss** - Automatic position closure at loss threshold (default -10%)

### Risk Management
- **Capital modes** - Fixed or percentage-based
- **Market filters** - Time to close, orderbook bias, probabilities
- **Liquidity monitoring** - Cancels orders on deterioration
- **Price floor** ⭐ **v1.1** - Optional protection against selling below buy price
- **Order timeouts** - Automatic cancellation after time limit

### Monitoring & UI
- **GUI launcher** - 6 configuration tabs, real-time logs, bot control
- **Telegram alerts** - Event notifications + hourly heartbeat
- **Persistent P&L** - Statistics survive `state.json` deletion
- **Auto-update** - Notifications for new versions

---

## 📦 Installation

### Standalone (Recommended)
**No Python installation required!**
- [Windows](https://github.com/KrisGravedigger/idk-about-your-opinion-bot/releases/latest) - `OpinionBot_Windows.zip`
- [Linux](https://github.com/KrisGravedigger/idk-about-your-opinion-bot/releases/latest) - `OpinionBot_Linux.zip`
- [macOS](https://github.com/KrisGravedigger/idk-about-your-opinion-bot/releases/latest) - `OpinionBot_macOS.zip`

### From Source (Python 3.10+)
```bash
git clone <repository-url>
cd opinion_trading_bot
pip install -r requirements.txt
python gui_launcher.py  # GUI
# or
python autonomous_bot_main.py  # CLI
```

---

## ⚙️ Configuration

### Configuration Priority

**IMPORTANT:** Settings saved through the GUI (`bot_config.json`) take priority over settings in `config.py`. The bot loads GUI settings first, then falls back to `config.py` for any missing values.

### Key Parameters (`config.py` or GUI)

**Capital:**
```python
CAPITAL_MODE = 'percentage'  # 'fixed' or 'percentage'
CAPITAL_AMOUNT_USDT = 20.0   # Fixed mode
CAPITAL_PERCENTAGE = 90.0    # Percentage mode
MIN_BALANCE_TO_CONTINUE_USDT = 50.0
```

**Market Filters:**
```python
MIN_HOURS_UNTIL_CLOSE = 30   # Minimum time to close
MAX_HOURS_UNTIL_CLOSE = None # Maximum (None = no limit)
ORDERBOOK_BALANCE_RANGE = (45, 80)  # % bids (45-80%)
OUTCOME_MIN_PROBABILITY = 0.30  # Min probability
OUTCOME_MAX_PROBABILITY = 0.84  # Max probability
```

**Pricing:**
```python
SPREAD_THRESHOLD_1 = 0.20  # Tiny: ≤$0.20
SPREAD_THRESHOLD_2 = 0.50  # Small: $0.21-$0.50
SPREAD_THRESHOLD_3 = 1.00  # Medium: $0.51-$1.00
IMPROVEMENT_TINY = 0.00    # Join queue
IMPROVEMENT_SMALL = 0.10   # +$0.10
IMPROVEMENT_MEDIUM = 0.20  # +$0.20
IMPROVEMENT_WIDE = 0.30    # +$0.30
```

**Stop-Loss:**
```python
ENABLE_STOP_LOSS = True
STOP_LOSS_TRIGGER_PERCENT = -10.0  # -10% loss
```

**Sell Order Repricing** ⭐ **v1.1:**
```python
ENABLE_SELL_ORDER_REPRICING = True
SELL_REPRICE_LIQUIDITY_THRESHOLD_PCT = 50.0  # Trigger at ≥50% liquidity drop
ALLOW_SELL_BELOW_BUY_PRICE = False  # Price floor protection
MAX_SELL_PRICE_REDUCTION_PCT = 5.0  # Max -5% from buy price
SELL_REPRICE_SCALE_MODE = 'best'  # 'best', 'second_best', 'liquidity_percent'
SELL_REPRICE_LIQUIDITY_TARGET_PCT = 30.0  # Target for liquidity_percent mode
ENABLE_DYNAMIC_SELL_PRICE_ADJUSTMENT = True  # Auto-return to higher price
SELL_REPRICE_LIQUIDITY_RETURN_PCT = 20.0  # Return threshold
```

**Telegram:**
```python
TELEGRAM_HEARTBEAT_INTERVAL_HOURS = 1.0  # Heartbeat every hour
```

---

## 🎛️ GUI Configuration Tool

### Features
- **6 tabs:** Capital, Market, Trading, Risk, Monitoring, Credentials
- **Real-time logs** with syntax highlighting
- **Start/Stop/Restart** with one click
- **Validation** before launch
- **Profile management** - Save/load different strategies

### Launch
```bash
python gui_launcher.py
```

### Tabs

**1. Capital** - Mode selection, sliders, tooltips  
**2. Market** - Scoring profiles, filters (time, bias, probability)  
**3. Trading** - Spread thresholds, improvements  
**4. Risk** - Stop-loss, **SELL repricing** ⭐, timeouts, liquidity  
**5. Monitoring** - Log level, Telegram (test button)  
**6. Credentials** - API keys (masked), RPC URL, Telegram

**Risk Tab - Sell Repricing** ⭐ **v1.1:**
- Enable/disable repricing
- Liquidity threshold (slider + text field)
- Scale mode (best/second_best/liquidity_percent)
- Liquidity target/return percentages
- Price floor protection
- Max reduction percentage
- Dynamic adjustment toggle

### Control Panel
- ▶️ **Start** / ⏹️ **Stop** / 🔄 **Restart**
- Status display (Running/Stopped, PID, runtime)
- **View Logs** / **Open Folder** / **View PnL** / **View State**

---

## 📱 Telegram Notifications

### Setup (2 minutes)
1. `@BotFather` → `/newbot` → Copy token
2. `@userinfobot` → Copy Chat ID
3. Add to `.env`:
```env
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_ID=your_chat_id
```
4. Test: `python telegram_notifications.py` or button in GUI

**Full guide:** [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)

### Notification Types
- 🚀 **Bot Start** - Stats, capital, settings
- ⛔ **Bot Stop** - Final stats, last logs
- 📍 **State Changes** - BUY/SELL placed
- 🛑 **Stop-Loss** - Trigger notification
- 🔄 **Repricing** ⭐ **v1.1** - SELL price decrease/increase
- 💓 **Heartbeat** - Every hour (silent)

---

## 🔧 How It Works

### Trading Cycle
```
1. SCANNING → Find best market (YES/NO)
2. BUY_PLACED → Place buy order
3. BUY_MONITORING → Monitor until filled (timeout 8h)
4. BUY_FILLED → Purchase completed
5. SELL_PLACED → Place sell order
6. SELL_MONITORING → Monitor + stop-loss + repricing
7. COMPLETED → Calculate P&L → Save stats
8. IDLE → Repeat (if AUTO_REINVEST=True)
```

### Market Scoring
- **Spread** - Wider = better (more room for profit)
- **Price balance** - 50/50 bid/ask = optimal
- **Hourglass pattern** - Orderbook shape
- **Volume 24h** - Higher = bonus
- **Bonus markets** - 1.5x multiplier from `bonus_markets.txt`

### Sell Order Repricing ⭐ **v1.1**

**Triggers:**
- Liquidity drop ≥ threshold (default 50%)
- Orderbook deterioration

**Modes:**
- **best** - Price of best order (bid+$0.01)
- **second_best** - Price of second order
- **liquidity_percent** - Target % liquidity (e.g., 30%)

**Dynamic Adjustment:**
- Automatic return to higher price when orderbook improves
- Return threshold: liquidity return % (default 20%)
- Never exceeds original sell price

**Price Floor Protection:**
- `ALLOW_SELL_BELOW_BUY_PRICE = False` → Won't sell below buy price
- `MAX_SELL_PRICE_REDUCTION_PCT = 5.0` → Max -5% from buy price

---

## 🛡️ Safety Features

### Capital Protection
- Min balance check before each cycle
- Position size validation (min 50 USDT default)
- Stop-loss at -10% loss
- Price floor for SELL orders ⭐ **v1.1**

### Order Protection
- Spread crossing prevention (always maker)
- Safety margins from opposite side
- Order timeouts (8h default)
- Liquidity monitoring (cancel on >25% drop)

### Operational Safety
- Graceful shutdown (Ctrl+C → save state)
- State persistence → Resume after crash
- Comprehensive logging
- Telegram alerts for critical events

---

## 🔍 Troubleshooting

**"Configuration errors found"**
→ Check `.env` (API_KEY, PRIVATE_KEY, MULTI_SIG_ADDRESS)

**"Insufficient balance"**
→ Increase USDT or decrease CAPITAL_AMOUNT/CAPITAL_PERCENTAGE

**"No markets found"**
→ Too restrictive filters or no active markets

**Order stuck "pending"**
→ Normal, waiting for fill. Cancel with Ctrl+C if needed.

**Telegram not working**
→ `python telegram_notifications.py` (test) → See [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)

**Repricing not working** ⭐ **v1.1**
→ Check `ENABLE_SELL_ORDER_REPRICING = True` + INFO level logs

### Debug Mode
```python
# config.py
LOG_LEVEL = "DEBUG"
```

### Reset State
```bash
python autonomous_bot_main.py --reset-state
```
(P&L stats in `pnl_stats.json` will remain)

---

## 📄 License & Disclaimer

⚠️ **RISKS:**
- **Bot can lose all capital**
- Markets are unpredictable
- Stop-loss/repricing are not foolproof
- Bugs may cause losses
- New features may have undiscovered issues

⚠️ **RESPONSIBILITY:**
- Test with small amounts
- Monitor regularly (use Telegram!)
- Never invest more than you can afford to lose
- Developers NOT responsible for losses
- This is NOT financial advice

**License:** MIT (see LICENSE)

---

## 🎉 What's New

### v1.1.0 ⭐ **Current**
- **Sell order repricing** - 3 modes, dynamic return to higher price
- **Price floor protection** - Optionally won't sell below buy price
- **Liquidity-based triggering** - Reacts to liquidity drops
- **GUI integration** - Full control in Risk tab
- **INFO level logging** - Repricing analysis in logs

### v1.0.0
- Standalone executables (Windows/Linux/macOS)
- Full-featured GUI (6 tabs)
- Welcome wizard
- Auto-update system
- Clickable help links

### v0.3
- Telegram notifications
- Persistent P&L statistics
- Stop-loss protection
- Market filters (time, bias, probability)
- YES/NO market support

---

## 📚 Documentation

- **README.md** (this file) - Main documentation
- **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)** - Telegram setup step-by-step
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Code architecture
- **[tests/README.md](tests/README.md)** - Testing guide

---

## 🤝 Support

**Problems?**
1. Read README
2. Check `opinion_farming_bot.log`
3. See [GitHub Issues](https://github.com/...)
4. Open new issue (include: version, error, logs, config without credentials)

**Contributing:** Pull requests welcome (fork → branch → PR)

---

**Happy Trading! 🤖💰**

*Remember: Test with small amounts, monitor logs, use Telegram alerts.*
