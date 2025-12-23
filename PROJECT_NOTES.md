# 📌 Project Overview: Opinion Trading Bot

**Status:** Production Ready (v0.2)  
**Last Updated:** December 2025  
**Platform:** Opinion.trade (BNB Chain)  
**Strategy:** Autonomous Liquidity Provision

---

## 🎯 Project Purpose

Autonomous trading bot for Opinion.trade prediction markets that maximizes airdrop points while generating trading profits through sophisticated market-making strategies.

### Key Objectives

1. **Airdrop Optimization** - Strategic market selection based on bonus multipliers and point-earning criteria
2. **Profit Generation** - Capture bid-ask spreads through maker orders
3. **Risk Management** - Comprehensive safety features including stop-loss and liquidity monitoring
4. **Automation** - Fully autonomous operation from market selection to position closing

---

## 📊 Current Status

### ✅ Completed Features

#### Core Trading Engine
- [x] Full state machine implementation (8 stages)
- [x] Autonomous trading cycle (IDLE → SCANNING → ... → COMPLETED)
- [x] State persistence across restarts
- [x] Multi-cycle operation with configurable limits

#### Market Intelligence
- [x] Market scanner with multi-factor scoring
- [x] Bonus market support (2x multiplier)
- [x] Filtering system (time, balance, liquidity)
- [x] Advanced scoring profiles (production_farming, test_quick_fill, balanced)

#### Pricing & Orders
- [x] Threshold-based pricing strategy
- [x] Dynamic spread-based improvements ($0.00-$0.30 adjustments)
- [x] Safety checks (spread crossing prevention)
- [x] Order placement and management

#### Monitoring & Risk
- [x] BUY order monitoring with liquidity checks
- [x] SELL order monitoring with stop-loss
- [x] Liquidity deterioration detection (bid drop, spread widening)
- [x] Order timeouts (24h default)
- [x] Stop-loss protection (-10% threshold)

#### Capital Management
- [x] Fixed and percentage-based position sizing
- [x] Balance validation and safety checks
- [x] Minimum position size enforcement
- [x] Airdrop point threshold warnings

#### Analytics
- [x] P&L calculation using Decimal precision
- [x] Trade statistics (wins, losses, win rate)
- [x] Session summaries
- [x] Trade history tracking

#### Infrastructure
- [x] Centralized logging (console + file)
- [x] Configuration validation
- [x] Error handling and recovery
- [x] Graceful shutdown (Ctrl+C)

### 🔄 In Progress

- [ ] CSV transaction logging (architecture defined, implementation pending)
- [ ] State synchronization with API (16-scenario matrix defined)

### 📋 Planned Features

#### High Priority
- [ ] Transaction CSV logging with detailed metrics
- [ ] State conflict resolution (local vs API)
- [ ] Data reconciliation engine
- [ ] Enhanced error reporting with structured format

#### Medium Priority
- [ ] Multi-market support (parallel positions)
- [ ] Telegram notifications
- [ ] Web dashboard for monitoring
- [ ] Backtesting framework

#### Low Priority
- [ ] Advanced strategies (momentum, mean reversion)
- [ ] Machine learning market selection
- [ ] GUI interface
- [ ] Mobile app

---

## 🏗️ Architecture

### Design Principles

1. **Modularity** - Clear separation of concerns (core, monitoring, strategies)
2. **State-Driven** - State machine ensures predictable behavior
3. **Safety-First** - Multiple layers of validation and risk management
4. **Persistence** - Resume from any interruption
5. **Configurability** - Extensive parameters without code changes

### Module Hierarchy

```
autonomous_bot_main.py (entry point)
    ↓
core/autonomous_bot.py (orchestrator)
    ↓
    ├─ core/capital_manager.py (position sizing)
    ├─ core/state_manager.py (persistence)
    ├─ market_scanner.py (opportunity discovery)
    ├─ strategies/pricing.py (price calculation)
    ├─ order_manager.py (order execution)
    ├─ monitoring/buy_monitor.py (BUY monitoring)
    ├─ monitoring/sell_monitor.py (SELL monitoring)
    └─ position_tracker.py (P&L calculation)
```

### State Machine Flow

```
┌────────┐
│  IDLE  │ ← Start/Resume
└────┬───┘
     ↓
┌─────────────┐
│  SCANNING   │ ← Find best market
└──────┬──────┘
       ↓
┌──────────────┐
│  BUY_PLACED  │ ← Order submitted
└──────┬───────┘
       ↓
┌─────────────────┐
│ BUY_MONITORING  │ ← Wait for fill + liquidity check
└────────┬────────┘
         ↓
┌─────────────┐
│ BUY_FILLED  │ ← Prepare SELL
└──────┬──────┘
       ↓
┌───────────────┐
│  SELL_PLACED  │ ← Order submitted
└───────┬───────┘
        ↓
┌──────────────────┐
│ SELL_MONITORING  │ ← Wait for fill + stop-loss check
└────────┬─────────┘
         ↓
┌───────────┐
│ COMPLETED │ ← Calculate P&L, update stats
└─────┬─────┘
      ↓
   (repeat)
```

---

## 🔧 Configuration Overview

### Capital Management

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `CAPITAL_MODE` | str | `'percentage'` | 'fixed' or 'percentage' |
| `CAPITAL_AMOUNT_USDT` | float | `20.0` | Fixed amount per position |
| `CAPITAL_PERCENTAGE` | float | `60.0` | % of balance per position |
| `MIN_BALANCE_TO_CONTINUE_USDT` | float | `20.0` | Exit if balance below |

### Pricing Strategy

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SPREAD_THRESHOLD_1` | float | `0.20` | Tiny spreads: ≤$0.20 |
| `SPREAD_THRESHOLD_2` | float | `0.50` | Small spreads: $0.21-$0.50 |
| `SPREAD_THRESHOLD_3` | float | `1.00` | Medium spreads: $0.51-$1.00 |
| `IMPROVEMENT_TINY` | float | `0.00` | No improvement (join queue) |
| `IMPROVEMENT_SMALL` | float | `0.10` | +$0.10 improvement |
| `IMPROVEMENT_MEDIUM` | float | `0.20` | +$0.20 improvement |
| `IMPROVEMENT_WIDE` | float | `0.30` | +$0.30 improvement |

### Risk Management

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_STOP_LOSS` | bool | `True` | Enable stop-loss protection |
| `STOP_LOSS_TRIGGER_PERCENT` | float | `-10.0` | Trigger at -10% loss |
| `LIQUIDITY_AUTO_CANCEL` | bool | `True` | Cancel on liquidity deterioration |
| `LIQUIDITY_BID_DROP_THRESHOLD` | float | `25.0` | Cancel if bid drops >25% |
| `LIQUIDITY_SPREAD_THRESHOLD` | float | `15.0` | Cancel if spread >15% |

### Monitoring

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `FILL_CHECK_INTERVAL_SECONDS` | int | `9` | Check order status every 9s |
| `BUY_ORDER_TIMEOUT_HOURS` | int | `24` | BUY timeout (hours) |
| `SELL_ORDER_TIMEOUT_HOURS` | int | `24` | SELL timeout (hours) |

---

## 📈 Performance Metrics

### Observed Performance (Limited Sample)

**Note:** Bot is in early production. These metrics are from initial testing:

- **Win Rate:** ~60% (small sample size)
- **Average P&L:** 3-5% per successful trade
- **Cycle Time:** 2-8 hours (depends on market activity)
- **Liquidity Detection:** Effective at identifying deterioration

### Optimization Opportunities

1. **Pricing Tuning** - Adjust improvement amounts for faster fills
2. **Market Selection** - Refine scoring weights for better opportunities
3. **Stop-Loss Threshold** - Balance between protection and false triggers
4. **Timeout Settings** - Adjust based on market volatility

---

## 🔒 Security & Safety

### Implemented Safeguards

#### Credentials
- ✅ Environment variables (.env) for sensitive data
- ✅ No hardcoded keys in code
- ✅ .gitignore prevents accidental commits
- ✅ Separate credentials from configuration

#### Capital Protection
- ✅ Minimum balance checks before trading
- ✅ Position size validation
- ✅ Platform constraint enforcement
- ✅ Balance queries before each order

#### Order Safety
- ✅ Spread crossing prevention (never take)
- ✅ Safety margins from opposite side
- ✅ Price validation before submission
- ✅ Order confirmation checks

#### Operational Safety
- ✅ Graceful shutdown with state save
- ✅ Error handling at all levels
- ✅ Comprehensive logging
- ✅ State validation on load

### Security Recommendations

1. **Use dedicated trading wallet** (not main holdings)
2. **Start with small capital** ($20-50 USDT)
3. **Monitor regularly** (check logs daily)
4. **Keep private key secure** (offline backup)
5. **Review configuration** before deployment

---

## 🐛 Known Issues & Limitations

### Current Limitations

1. **Single Position** - Only one market at a time
2. **Manual Config Updates** - No runtime configuration changes
3. **Limited Historical Data** - No long-term analytics database
4. **No GUI** - Command-line only

### Known Issues

1. **State Conflicts** - Rare cases where local state and API disagree (architecture for fix defined)
2. **Network Errors** - Intermittent API failures require retry
3. **Orderbook Parsing** - Assumes unsorted orderbooks (Opinion.trade quirk)

### Mitigations

- State conflicts: Manual state.json reset available
- Network errors: Comprehensive error handling + retry logic
- Orderbook: Using max/min instead of [0] indexing

---

## 🧪 Testing Strategy

### Levels of Testing

1. **Unit Tests** (in `tests/` directory)
   - Individual module functionality
   - Edge cases and error conditions
   - Mock API responses

2. **Integration Tests**
   - Module interaction
   - State transitions
   - End-to-end cycle

3. **Production Testing**
   - Small capital deployment
   - Single-cycle runs (`--max-cycles 1`)
   - Log analysis

### Testing Checklist Before Deployment

- [ ] Config validation passes
- [ ] Credentials loaded correctly
- [ ] Balance queries work
- [ ] Market scanner returns results
- [ ] Order placement succeeds (small test order)
- [ ] State persistence works (create/load/save)
- [ ] Graceful shutdown functions
- [ ] Logs are readable and informative

---

## 📚 Documentation

### Available Documentation

1. **README.md** - Comprehensive user guide
2. **Inline Comments** - Detailed code documentation
3. **Docstrings** - Function/class documentation
4. **config.py** - Configuration parameter descriptions
5. **This Note** - Project overview for developers

### Documentation Standards

- All public functions have docstrings
- Non-obvious logic has inline comments
- Configuration parameters have descriptions
- Modules have header documentation

---

## 🔄 Development Workflow

### Current Workflow

1. **Planning** - Define feature scope and architecture
2. **Implementation** - Code in isolated modules
3. **Testing** - Unit tests + small capital test
4. **Documentation** - Update README and docstrings
5. **Deployment** - Gradual rollout with monitoring

### Version Control

- **Main Branch** - Production-ready code
- **Feature Branches** - Work-in-progress features
- **Legacy Folder** - Old code (not in Git)
- **Tests Folder** - Test files (not in Git)

### Release Process

1. Test thoroughly with small capital
2. Update version number in README
3. Update CHANGELOG (if maintained)
4. Tag release in Git
5. Document any breaking changes

---

## 🤝 Contributing

### Areas for Contribution

1. **Features** - New strategies, monitoring improvements
2. **Bug Fixes** - Address known issues
3. **Documentation** - Improve clarity, add examples
4. **Testing** - Expand test coverage
5. **Performance** - Optimize slow operations

### Contribution Guidelines

1. Fork repository
2. Create feature branch (`feature/your-feature-name`)
3. Write/update tests
4. Update documentation
5. Submit pull request with clear description

---

## 📞 Contact & Support

### Resources

- **Issues:** GitHub Issues for bug reports
- **Documentation:** Comprehensive README.md
- **Code:** Fully commented source code
- **Logs:** opinion_farming_bot.log for debugging

### Getting Help

1. Check README.md troubleshooting section
2. Review log files for errors
3. Search existing GitHub issues
4. Create new issue with full details

---

## ⚖️ Legal

### Disclaimer

This software is provided "as is" without warranty. Trading involves risk of loss. Users are responsible for their own trading decisions and any resulting losses. The developers provide no financial advice and are not liable for any damages.

### License

MIT License - Open source, use at your own risk.

---

## 🎯 Success Metrics

### Bot Effectiveness

- **Operational Uptime** - Ability to run continuously without errors
- **Win Rate** - Percentage of profitable trades
- **Average P&L** - Profit per trade
- **Risk Management** - Proper stop-loss and liquidity detection
- **Capital Preservation** - Avoidance of catastrophic losses

### Development Success

- **Code Quality** - Maintainable, documented, tested
- **User Experience** - Clear logs, easy configuration
- **Reliability** - Handles errors gracefully
- **Performance** - Efficient operation without slowdowns

---

**Last Updated:** December 2025  
**Version:** 0.2 (Beta)  
**Maintainer:** Kris Gravedigger

---

## Quick Commands Reference

```bash
# Standard operation
python autonomous_bot_main.py

# Limited cycles (testing)
python autonomous_bot_main.py --max-cycles 5

# Fresh start (clear state)
python autonomous_bot_main.py --reset-state

# Stop bot (graceful)
Ctrl+C

# View logs
tail -f opinion_farming_bot.log

# Check state
cat state.json
```
