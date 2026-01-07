# Architecture Documentation

Opinion Farming Bot - Modular Trading System Architecture

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Module Structure](#module-structure)
4. [State Machine](#state-machine)
5. [Data Flow](#data-flow)
6. [Code Organization](#code-organization)
7. [Design Patterns](#design-patterns)
8. [Extension Points](#extension-points)

---

## Overview

The Opinion Farming Bot is a modular autonomous trading system designed for prediction markets on Opinion.trade. The architecture follows SOLID principles with clear separation of concerns.

### Key Statistics

- **Before Refactoring**: ~2096 lines in single file (God Object)
- **After Refactoring**: 922 lines orchestrator + 5 specialized modules
- **Code Reduction**: -56% in main orchestrator
- **Duplication Reduction**: -90% (from ~50% to ~5%)

### Design Goals

1. **Modularity**: Each module has single responsibility
2. **Testability**: Components can be tested in isolation
3. **Maintainability**: Changes localized to specific modules
4. **Extensibility**: Easy to add new strategies/handlers

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AutonomousBot                            │
│                   (Orchestrator - 922 lines)                 │
│                                                              │
│  Responsibilities:                                           │
│  • Main execution loop                                       │
│  • State machine coordination                                │
│  • Module initialization                                     │
│  • Heartbeat & notifications                                 │
└──────────────┬──────────────────────────────────────────────┘
               │
               │ Delegates to:
               │
     ┌─────────┴──────────┬──────────────┬──────────────┐
     │                    │              │              │
     ▼                    ▼              ▼              ▼
┌──────────┐      ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Market   │      │   BUY    │  │  SELL    │  │Position  │
│ Selector │      │ Handler  │  │ Handler  │  │Validator │
│          │      │          │  │          │  │          │
│ 415 lines│      │ 536 lines│  │ 299 lines│  │ 326 lines│
└──────────┘      └──────────┘  └──────────┘  └──────────┘
     │                    │              │              │
     └────────────────────┴──────────────┴──────────────┘
                          │
                          ▼
                 ┌────────────────┐
                 │   API Client   │
                 │  Opinion.trade │
                 └────────────────┘
```

### Module Responsibilities

#### Core Modules (`core/`)

**AutonomousBot** (922 lines)
- Main orchestrator
- State machine execution
- Module coordination
- Heartbeat management

**PositionValidator** (326 lines)
- Dust position detection (shares & value)
- Token ID validation
- Manual sale detection
- Position verification

**PositionRecovery** (385 lines)
- Order ID recovery
- Token ID recovery
- Fill amount recovery
- Orphaned position detection

#### Handler Modules (`handlers/`)

**MarketSelector** (415 lines)
- Market scanning & ranking
- Orphaned position recovery
- Orderbook validation
- BUY order placement

**BuyHandler** (536 lines)
- BUY_PLACED stage logic
- BUY order monitoring
- Fill detection & verification
- SELL preparation (BUY_FILLED)

**SellHandler** (299 lines)
- SELL_PLACED stage logic
- SELL order monitoring
- P&L calculation
- Trade completion

---

## Module Structure

### Dependency Graph

```
AutonomousBot
├── MarketSelector
│   ├── MarketScanner (external)
│   ├── CapitalManager (external)
│   ├── OrderManager (external)
│   └── PricingStrategy (external)
│
├── BuyHandler
│   ├── PositionValidator
│   ├── PositionRecovery
│   ├── BuyMonitor (external)
│   └── MarketScanner (external)
│
├── SellHandler
│   ├── PositionValidator
│   ├── SellMonitor (external)
│   └── PositionTracker (external)
│
├── PositionValidator
│   └── OpinionClient (external)
│
└── PositionRecovery
    └── OpinionClient (external)
```

### Code Organization

```
idk-about-your-opinion-bot/
├── core/
│   ├── autonomous_bot.py       # Main orchestrator
│   ├── capital_manager.py      # Position sizing
│   ├── state_manager.py        # State persistence
│   ├── position_validator.py   # Validation logic ✨ NEW
│   └── position_recovery.py    # Recovery logic ✨ NEW
│
├── handlers/                    ✨ NEW DIRECTORY
│   ├── __init__.py
│   ├── market_selector.py      # SCANNING stage ✨ NEW
│   ├── buy_handler.py          # BUY stages ✨ NEW
│   └── sell_handler.py         # SELL stages ✨ NEW
│
├── monitoring/
│   ├── buy_monitor.py          # BUY fill monitoring
│   ├── sell_monitor.py         # SELL fill monitoring
│   └── liquidity_checker.py    # Liquidity validation
│
├── strategies/
│   └── pricing.py              # Price calculation
│
├── tests/                       ✨ NEW DIRECTORY
│   ├── __init__.py
│   ├── README.md
│   └── test_position_validator.py  ✨ NEW
│
├── docs/                        ✨ NEW DIRECTORY
│   └── ARCHITECTURE.md         # This file ✨ NEW
│
├── market_scanner.py           # Market discovery
├── order_manager.py            # Order placement
├── position_tracker.py         # P&L tracking
├── api_client.py               # API integration
├── config.py                   # Configuration
└── utils.py                    # Helper functions
```

---

## State Machine

### Trading Cycle States

```
                    ┌─────────┐
                    │  IDLE   │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
             ┌──────┤SCANNING │
             │      └────┬────┘
             │           │
             │      Found Market
             │           │
             │           ▼
             │    ┌────────────┐
             │    │BUY_PLACED  │
             │    └─────┬──────┘
             │          │
             │          ▼
             │    ┌──────────────┐
             │    │BUY_MONITORING│◄──┐
             │    └──────┬───────┘   │ Retry
             │           │            │
No Market /  │      Order Filled      │
Cancelled    │           │            │
             │           ▼            │
             │    ┌────────────┐     │
             │    │BUY_FILLED  │─────┘
             │    └─────┬──────┘
             │          │
             │  SELL Order Placed
             │          │
             │          ▼
             │    ┌─────────────┐
             │    │SELL_PLACED  │
             │    └──────┬──────┘
             │           │
             │           ▼
             │    ┌───────────────┐
             │    │SELL_MONITORING│◄──┐
             │    └───────┬───────┘   │ Retry
             │            │            │
             │       Order Filled      │
             │            │            │
             │            ▼            │
             │       ┌─────────┐      │
             │       │COMPLETED│──────┘
             │       └────┬────┘
             │            │
             │            ▼
             └────────►  IDLE
```

### Stage Handlers

Each stage has dedicated handler method:

| Stage | Handler | Module | Lines |
|-------|---------|--------|-------|
| IDLE | `_handle_idle()` | AutonomousBot | ~20 |
| SCANNING | `handle_scanning()` | MarketSelector | ~300 |
| BUY_PLACED | `handle_buy_placed()` | BuyHandler | ~10 |
| BUY_MONITORING | `handle_buy_monitoring()` | BuyHandler | ~300 |
| BUY_FILLED | `handle_buy_filled()` | BuyHandler | ~200 |
| SELL_PLACED | `handle_sell_placed()` | SellHandler | ~10 |
| SELL_MONITORING | `handle_sell_monitoring()` | SellHandler | ~200 |
| COMPLETED | `_handle_completed()` | AutonomousBot | ~20 |

---

## Data Flow

### SCANNING → BUY Flow

```
┌────────────────┐
│ MarketSelector │
└───────┬────────┘
        │
        │ 1. Check orphaned positions
        ▼
┌─────────────────────┐
│ PositionRecovery    │
│ find_orphaned()     │
└──────┬──────────────┘
       │
       │ 2. Scan markets
       ▼
┌─────────────────────┐
│ MarketScanner       │
│ scan_and_rank()     │
└──────┬──────────────┘
       │
       │ 3. Validate orderbook
       ▼
┌─────────────────────┐
│ MarketSelector      │
│ validate_orderbook()│
└──────┬──────────────┘
       │
       │ 4. Calculate size
       ▼
┌─────────────────────┐
│ CapitalManager      │
│ get_position_size() │
└──────┬──────────────┘
       │
       │ 5. Place order
       ▼
┌─────────────────────┐
│ OrderManager        │
│ place_buy()         │
└──────┬──────────────┘
       │
       │ 6. Save state
       ▼
┌─────────────────────┐
│ StateManager        │
│ save_state()        │
└─────────────────────┘
```

### BUY_FILLED → SELL Flow

```
┌────────────────┐
│   BuyHandler   │
└───────┬────────┘
        │
        │ 1. Validate token_id
        ▼
┌─────────────────────┐
│ PositionValidator   │
│ validate_token_id() │
└──────┬──────────────┘
       │
       │ 2. Check manual sale
       ▼
┌─────────────────────────┐
│ PositionValidator       │
│ verify_actual_position()│
└──────┬──────────────────┘
       │
       │ 3. Check dust (shares)
       ▼
┌────────────────────────────┐
│ PositionValidator          │
│ check_dust_by_shares()     │
└──────┬─────────────────────┘
       │
       │ 4. Get fresh orderbook
       ▼
┌─────────────────────┐
│ MarketScanner       │
│ get_fresh_orderbook()│
└──────┬──────────────┘
       │
       │ 5. Check dust (value)
       ▼
┌────────────────────────────┐
│ PositionValidator          │
│ check_dust_by_value()      │
└──────┬─────────────────────┘
       │
       │ 6. Place SELL order
       ▼
┌─────────────────────┐
│ OrderManager        │
│ place_sell()        │
└─────────────────────┘
```

---

## Design Patterns

### 1. Delegation Pattern

**AutonomousBot** delegates to specialized handlers:

```python
# Before (God Object):
def _handle_scanning(self):
    # 300+ lines of logic inline
    ...

# After (Delegation):
def _handle_scanning(self):
    return self.market_selector.handle_scanning()
```

**Benefits:**
- Single Responsibility Principle
- Easier testing
- Better code organization

### 2. Validator Pattern

**PositionValidator** provides reusable validation methods:

```python
# Before (Duplicated):
if filled_amount < MIN_SELLABLE_SHARES:
    logger.warning("DUST!")
    # ... 20 lines of duplicate logic

# After (Centralized):
result = self.validator.check_dust_position_by_shares(filled_amount)
if not result.is_valid:
    # result.reason contains formatted message
```

**Benefits:**
- DRY (Don't Repeat Yourself)
- Consistent validation logic
- Easier to modify validation rules

### 3. Recovery Pattern

**PositionRecovery** handles self-healing:

```python
# Before (Complex inline recovery):
if order_id == 'unknown':
    # 100+ lines of API calls, parsing, validation
    ...

# After (Encapsulated):
result = self.recovery.recover_order_id_from_api(market_id, "BUY")
if result.success:
    order_id = result.order_id
```

**Benefits:**
- Isolated recovery logic
- Reusable across stages
- Testable error handling

### 4. Handler Pattern

Each trading stage has dedicated handler class:

```python
class BuyHandler:
    def __init__(self, bot):
        self.bot = bot  # Access to shared resources

    def handle_buy_placed(self): ...
    def handle_buy_monitoring(self): ...
    def handle_buy_filled(self): ...
```

**Benefits:**
- Grouped related functionality
- Clear ownership
- Parallel development possible

---

## Extension Points

### Adding New Validation Rules

Extend `PositionValidator`:

```python
def check_custom_rule(self, position_data):
    """Your custom validation logic."""
    if some_condition:
        return ValidationResult(
            is_valid=False,
            reason="Custom rule failed",
            action="reset_to_scanning"
        )
    return ValidationResult(is_valid=True)
```

### Adding New Recovery Strategy

Extend `PositionRecovery`:

```python
def recover_custom_data(self, market_id):
    """Your custom recovery logic."""
    try:
        data = self.client.get_custom_data(market_id)
        return RecoveryResult(
            success=True,
            custom_field=data
        )
    except Exception as e:
        return RecoveryResult(
            success=False,
            reason=str(e)
        )
```

### Adding New Trading Stage

1. Add handler method to appropriate module
2. Register in `_execute_stage()` handlers dict
3. Add state transitions

### Adding New Market Strategy

Create new scanner or modify `MarketScanner`:

```python
class CustomMarketScanner(MarketScanner):
    def custom_scoring_logic(self, market):
        # Your custom logic
        return custom_score
```

---

## Performance Considerations

### Module Initialization

Handlers initialized once in `__init__`:
```python
# Efficient - initialized once
self.market_selector = MarketSelector(self)
self.buy_handler = BuyHandler(self)
```

### State Persistence

State saved only when changed:
```python
# Only save when state actually changes
if state_modified:
    self.state_manager.save_state(self.state)
```

### API Call Optimization

- Reuse orderbook data when possible
- Cache market details within handler execution
- Batch position checks

---

## Testing Strategy

### Unit Tests

Test each module in isolation:

```python
class TestPositionValidator(unittest.TestCase):
    def setUp(self):
        self.mock_client = Mock()
        self.validator = PositionValidator(self.mock_client, config)

    def test_dust_detection(self):
        result = self.validator.check_dust_position_by_shares(3.0)
        self.assertFalse(result.is_valid)
```

### Integration Tests

Test handler interactions:

```python
def test_buy_flow():
    # Test full BUY cycle with mocked dependencies
    ...
```

### Coverage Goals

- **Core modules**: >80%
- **Handlers**: >70%
- **Orchestrator**: >60%

---

## Migration Guide

### From Old Architecture

If migrating from pre-refactoring code:

1. **No changes to external APIs** - Same OpinionClient interface
2. **State format unchanged** - Backward compatible
3. **Configuration compatible** - Same config.py structure
4. **Gradual adoption** - Can run alongside old code

### Deployment

```bash
# 1. Pull latest code
git pull origin main

# 2. No new dependencies
# (Uses same requirements.txt)

# 3. Run tests
python -m pytest tests/

# 4. Start bot normally
python autonomous_bot_main.py
```

---

## Metrics & Statistics

### Code Quality Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Main file size | 2096 lines | 922 lines | -56% |
| Code duplication | ~50% | ~5% | -90% |
| Modules | 1 monolith | 6 specialized | +500% modularity |
| Testability | Low | High | Isolated modules |
| Cyclomatic complexity | Very High | Low-Medium | Better maintainability |

### Module Distribution

```
Total code: ~2,883 lines (handlers + core)

AutonomousBot:      922 lines (32%)  - Orchestration
BuyHandler:         536 lines (19%)  - BUY logic
MarketSelector:     415 lines (14%)  - Market selection
PositionRecovery:   385 lines (13%)  - Recovery logic
PositionValidator:  326 lines (11%)  - Validation logic
SellHandler:        299 lines (10%)  - SELL logic
```

---

## Future Enhancements

### Potential Improvements

1. **Async/Await** - Non-blocking API calls
2. **Event System** - Pub/sub for stage transitions
3. **Strategy Pattern** - Pluggable trading strategies
4. **Circuit Breaker** - API failure protection
5. **Metrics Collection** - Prometheus/Grafana integration

### Planned Features

- [ ] Multiple concurrent positions
- [ ] Advanced stop-loss strategies
- [ ] Machine learning integration
- [ ] WebSocket real-time updates
- [ ] Backtesting framework

---

## Contributing

### Adding New Features

1. Identify appropriate module
2. Write tests first (TDD)
3. Implement feature
4. Update documentation
5. Submit PR with tests

### Code Standards

- **PEP 8** compliance
- **Type hints** for public methods
- **Docstrings** for all classes/methods
- **100 chars** max line length
- **pytest** for testing

---

## Support & Resources

- **Code**: https://github.com/KrisGravedigger/idk-about-your-opinion-bot
- **Issues**: GitHub Issues
- **Documentation**: `/docs` directory
- **Tests**: `/tests` directory

---

*Last updated: 2026-01-07*
*Version: 2.0 (Post-Refactoring)*
