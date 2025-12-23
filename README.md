# Opinion Farming Bot 🤖

Automated trading bot for Opinion.trade - a prediction market platform on BNB Chain. The bot implements a liquidity provision strategy designed to maximize airdrop points while generating trading profits.

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [What Does This Bot Do?](#-what-does-this-bot-do)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Running the Bot](#-running-the-bot)
- [Stage Descriptions](#-stage-descriptions)
- [Understanding the Output](#-understanding-the-output)
- [Troubleshooting](#-troubleshooting)
- [Safety & Security](#-safety--security)

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up credentials
cp .env.example .env
# Edit .env with your API key and wallet details

# 3. Add bonus markets (optional)
# Edit bonus_markets.txt with market IDs

# 4. Run the bot stages
python mvp_stage1.py  # Scan markets
python mvp_stage2.py  # Place order
python mvp_stage3.py  # Monitor for fills (passive)
# OR
python mvp_stage5.py  # Monitor with competitive re-pricing
python mvp_stage4.py  # Flip position (after BUY fills)
```

---

## 🎯 What Does This Bot Do?

The bot provides liquidity to prediction markets on Opinion.trade by:

1. **Finding Opportunities** - Scans all active markets to find ones with wide spreads (high profit potential) and bonus point multipliers

2. **Placing Strategic Orders** - Places limit BUY orders at optimal prices within the spread

3. **Competitive Monitoring** - Watches for competitors and automatically re-prices to stay competitive (up to 5 times)

4. **Position Flipping** - After buying tokens, automatically places SELL order to complete the cycle

5. **Continuous Operation** - Can automatically reinvest and find new opportunities

### Strategy Summary

```
Wide Spread Market Detected
         │
         ▼
┌─────────────────────┐
│   Place BUY Order   │  ◄── Stage 2
│   (near ask price)  │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Monitor Orderbook  │  ◄── Stage 3 or 5
│  (detect fills/     │
│   competition)      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   BUY Order Fills   │
│                     │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Place SELL Order   │  ◄── Stage 4
│  (near bid price)   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  SELL Order Fills   │
│  Position Closed    │
│  P&L Calculated     │
└─────────────────────┘
         │
         ▼
    🔄 Reinvest?
         │
    Yes ─┴─ No
     │      │
     ▼      ▼
   Stage 1  Exit
```

---

## 📦 Installation

### Requirements

- Python 3.10 or higher
- BNB Chain wallet with:
  - USDT for trading
  - Small amount of BNB for gas fees

### Steps

1. **Clone or download the bot files**

2. **Create virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment file**
   ```bash
   cp .env.example .env
   ```

5. **Edit `.env` with your credentials** (see Configuration below)

---

## ⚙️ Configuration

### Required: `.env` File

Create a `.env` file with your credentials:

```bash
API_KEY=your_opinion_trade_api_key
PRIVATE_KEY=0xYourWalletPrivateKey
MULTI_SIG_ADDRESS=0xYourWalletAddress
```

⚠️ **NEVER share or commit your `.env` file!**

### Optional: `config.py` Settings

Key parameters you might want to adjust in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TOTAL_CAPITAL_USDT` | 1000 | Total capital for trading |
| `CAPITAL_ALLOCATION_PERCENT` | 100 | % of capital per market |
| `AUTO_REINVEST` | True | Auto-find next market after cycle |
| `MAX_REPRICING_ATTEMPTS` | 5 | Max re-price attempts before abandoning |
| `PRICE_POSITION_BASE_PERCENT` | 95 | How aggressive to price (higher = more aggressive) |

### Optional: `bonus_markets.txt`

Add market IDs that earn bonus airdrop points:

```
# One market ID per line
813
914
1025
```

---

## 🎮 Running the Bot

### Stage 1: Market Scanner
```bash
python mvp_stage1.py
```

**What it does:** Scans all active markets and shows top 10 by opportunity score.

**Output:** Formatted table with:
- Market ID and title
- Spread percentage
- Best bid/ask prices
- Score (spread × bonus multiplier)

**When to use:** Before starting a new trading cycle.

---

### Stage 2: Auto Order Placement
```bash
python mvp_stage2.py
```

**What it does:**
1. Runs market scanner
2. Selects best market
3. Calculates optimal price
4. Places limit BUY order
5. Saves state to `state.json`

**Prerequisites:** None (starts fresh)

**Next step:** Run Stage 3 or Stage 5 to monitor

---

### Stage 3: Passive Fill Monitor
```bash
python mvp_stage3.py
```

**What it does:** Monitors your order every 9 seconds until it fills.

**When to use:** When you want simple monitoring without competitive re-pricing.

**Prerequisites:** Stage 2 must have been run (order placed)

---

### Stage 4: Auto Flip (SELL)
```bash
python mvp_stage4.py
```

**What it does:**
1. Loads state (after BUY filled)
2. Places SELL order at calculated price
3. Monitors until SELL fills
4. Calculates and displays P&L
5. If `AUTO_REINVEST=True`, starts new cycle

**Prerequisites:** BUY order must be filled (Stage 3 or 5 completed)

---

### Stage 5: Competitive Re-Pricing ⭐
```bash
python mvp_stage5.py
```

**What it does:**
1. Monitors orderbook for competitors
2. If outbid by >0.5%, automatically re-prices
3. Uses "gradual capitulation" strategy
4. After 5 re-prices, abandons market

**When to use:** In competitive markets where you might get outbid.

**Capitulation Logic:**
- Won't drop below 55-75% of initial price
- Prevents "race to bottom"

---

## 📊 Understanding the Output

### Market Scanner Table
```
┌──────┬────────────────────────────────────┬────────┬──────────┬──────────┬────────┐
│ Rank │ Market ID & Title                  │ Spread │ Best Bid │ Best Ask │ Score  │
├──────┼────────────────────────────────────┼────────┼──────────┼──────────┼────────┤
│  1   │ 813: BTC $100k by 2025? 🌟        │ 15.2%  │   $0.42  │   $0.58  │  30.40 │
└──────┴────────────────────────────────────┴────────┴──────────┴──────────┴────────┘
```

- **Spread:** Gap between bid and ask (higher = more profit potential)
- **Score:** Spread × bonus multiplier (🌟 markets get 2x)

### Log Messages

| Symbol | Meaning |
|--------|---------|
| ✅ | Success |
| ❌ | Error/Failure |
| ⚠️ | Warning |
| 🔄 | Action in progress |
| 💰 | Money/P&L related |
| 📊 | Data/Analysis |
| 🌟 | Bonus market |

### P&L Summary
```
💰 POSITION CLOSED - P&L SUMMARY:
   Buy cost: 1,000.00 USDT
   Sell proceeds: 1,055.12 USDT
   Net P&L: +$55.12 (+5.51%)
```

---

## 🔧 Troubleshooting

### "Configuration errors found"
- Check that `.env` file exists and has all required values
- Verify API_KEY is valid
- Verify PRIVATE_KEY is correct format (64 hex characters)

### "No markets found"
- Opinion.trade might have no active markets
- Check your internet connection
- Try again later

### "Insufficient balance"
- Check your USDT balance on Opinion.trade
- Reduce `TOTAL_CAPITAL_USDT` in config

### "Order cancelled by system"
- Market may have been resolved
- Run Stage 1 to find new market

### Bot stuck on "Order pending..."
- This is normal - order is waiting to be filled
- Press Ctrl+C to stop monitoring
- You can resume later with same stage

### "Failed to place order"
- Check if you have enough USDT
- Check if you have enough BNB for gas
- Verify API key is valid

---

## 🔒 Safety & Security

### DO ✅
- Keep `.env` file secure and never share it
- Use a dedicated trading wallet (not your main wallet)
- Start with small amounts to test
- Monitor the bot regularly
- Keep backup of your private key offline

### DON'T ❌
- Never commit `.env` to Git
- Never share your private key
- Never run on untrusted computers
- Never leave large amounts unmonitored

### State File
The bot saves its state to `state.json`. This file:
- Tracks current order and position
- Allows resuming after interruptions
- Should be backed up if you stop mid-cycle

---

## 📁 File Structure

```
opinion_farming_bot/
├── config.py           # All configuration parameters
├── api_client.py       # Opinion.trade API wrapper
├── market_scanner.py   # Market discovery & ranking
├── order_manager.py    # Order placement & management
├── position_tracker.py # Position & P&L tracking
├── logger_config.py    # Logging setup
├── utils.py            # Helper functions
├── mvp_stage1.py       # Stage 1: Market Scanner
├── mvp_stage2.py       # Stage 2: Auto Order Placement
├── mvp_stage3.py       # Stage 3: Passive Fill Monitor
├── mvp_stage4.py       # Stage 4: Auto Flip (SELL)
├── mvp_stage5.py       # Stage 5: Competitive Re-Pricing
├── .env.example        # Template for credentials
├── .env                # Your credentials (create this)
├── .gitignore          # Git ignore rules
├── requirements.txt    # Python dependencies
├── bonus_markets.txt   # Bonus market IDs
├── state.json          # Bot state (auto-generated)
└── README.md           # This documentation
```

---

## 📞 Support

If you encounter issues:

1. Check the log file: `opinion_farming_bot.log`
2. Review this README's Troubleshooting section
3. Verify your configuration in `.env` and `config.py`

---

## ⚖️ Disclaimer

This bot is for educational purposes. Trading prediction markets involves risk. Only trade with funds you can afford to lose. The developers are not responsible for any financial losses.

---

**Happy Farming! 🌾**
