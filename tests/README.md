# Tests

Unit tests for the Opinion Farming Bot.

## Running Tests

### Run all tests:
```bash
python -m pytest tests/
```

### Run specific test file:
```bash
python -m pytest tests/test_position_validator.py
```

### Run with coverage:
```bash
python -m pytest tests/ --cov=. --cov-report=html
```

### Run specific test:
```bash
python -m pytest tests/test_position_validator.py::TestPositionValidator::test_check_dust_position_by_shares_valid
```

## Test Structure

```
tests/
├── __init__.py
├── README.md (this file)
├── test_position_validator.py - Tests for PositionValidator
├── test_position_recovery.py  - Tests for PositionRecovery (TODO)
├── test_buy_handler.py        - Tests for BuyHandler (TODO)
├── test_sell_handler.py       - Tests for SellHandler (TODO)
└── test_market_selector.py    - Tests for MarketSelector (TODO)
```

## Writing Tests

Tests use Python's built-in `unittest` framework with `unittest.mock` for mocking dependencies.

### Example test structure:

```python
import unittest
from unittest.mock import Mock
from your_module import YourClass

class TestYourClass(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.mock_dependency = Mock()
        self.instance = YourClass(self.mock_dependency)

    def test_your_method(self):
        """Test description."""
        # Arrange
        expected_result = "expected"

        # Act
        result = self.instance.your_method()

        # Assert
        self.assertEqual(result, expected_result)
```

## Coverage Goals

- **Core modules**: >80% coverage
  - `position_validator.py`
  - `position_recovery.py`

- **Handlers**: >70% coverage
  - `buy_handler.py`
  - `sell_handler.py`
  - `market_selector.py`

- **Orchestrator**: >60% coverage
  - `autonomous_bot.py` (focus on critical paths)

## Mocking Strategy

### External Dependencies

Mock all external API calls:
```python
self.mock_client.get_market.return_value = Mock(yes_token_id="0x123")
```

### Configuration

Use minimal test config:
```python
self.config = {
    'MIN_ORDER_VALUE_USDT': 1.30,
    'MIN_SELLABLE_SHARES': 5.0
}
```

### State Management

Mock state manager for isolation:
```python
self.mock_state_manager = Mock()
self.mock_state_manager.load_state.return_value = {'stage': 'IDLE'}
```

## Continuous Integration

Tests can be integrated into CI/CD pipeline:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pip install pytest pytest-cov
    pytest tests/ --cov=. --cov-fail-under=70
```

## Test Data

Test fixtures and mock data are defined in each test file's `setUp()` method for clarity and isolation.

## Known Issues

### Pre-Refactoring Test Suite Status

The codebase underwent major refactoring (Jan 2026) that reduced `autonomous_bot.py` by 56% and eliminated 90% code duplication. The pre-existing test suite needs updating to match the new architecture.

**Current Test Results: 56/76 passing (74%)**

#### ✅ Passing Tests (56)
- `test_autonomous_bot.py`: 5/5 ✓
- `test_capital_manager.py`: 6/6 ✓
- `test_liquidity_checker.py`: 6/6 ✓
- `test_market_scanner.py`: 5/6 (83%)
- `test_position_validator.py`: 12/13 (92%) ⭐ New test suite
- `test_pricing.py`: 4/7 (57%)
- `test_scoring.py`: 7/7 ✓
- `test_state_manager.py`: 6/6 ✓
- `test_buy_monitor.py`: 5/6 (83%)
- `test_sell_monitor.py`: 0/9 (needs update)
- `test_integration.py`: 0/5 (needs update)

#### ❌ Tests Requiring Updates (20 failures)

**1. Integration Tests (5 failures)** - `test_integration.py`
- **Issue**: Mock client missing new methods (`get_all_active_markets`, `get_significant_positions`, `cleanup_resolved_positions`)
- **Cause**: Refactored handlers expect updated API client interface
- **Fix Required**: Update `IntegrationMockClient` to implement all current API methods

**2. SELL Monitor Tests (9 failures)** - `test_sell_monitor.py`
- **Issue**: All tests expect state passed as `state` parameter, but `SellMonitor` now expects `bot.state['current_position']`
- **Cause**: Handler refactoring changed how state is accessed
- **Fix Required**: Update test setup to pass full bot state structure
- **Example**:
  ```python
  # Old (failing)
  state = {'market_id': 813, 'avg_fill_price': 0.066}
  monitor = SellMonitor(config, client, state)

  # New (correct)
  bot_state = {
      'current_position': {
          'market_id': 813,
          'avg_fill_price': 0.066,
          'token_id': 1626,
          'filled_amount': 100.0
      }
  }
  monitor = SellMonitor(config, client, bot_state)
  ```

**3. Pricing Tests (3 failures)** - `test_pricing.py`
- **Issue**: Tests expect old multiplier-based pricing (`BUY_MULTIPLIER: 1.10`)
- **Cause**: Pricing strategy changed to threshold-based (spread-dependent improvements)
- **Fix Required**: Update tests to use threshold configuration
- **Example**:
  ```python
  # Old config (failing)
  config = {'BUY_MULTIPLIER': 1.10, 'SELL_MULTIPLIER': 0.90}

  # New config (correct)
  config = {
      'SPREAD_THRESHOLD_1': 0.20,
      'IMPROVEMENT_TINY': 0.00,
      'IMPROVEMENT_SMALL': 0.10,
      # ... threshold-based params
  }
  ```

**4. BUY Monitor Test (1 failure)** - `test_buy_monitor.py`
- **Issue**: Wei conversion not applied when extracting from trades
- **Fix Required**: Verify wei-to-normal conversion logic in extraction path

**5. Market Scanner Test (1 failure)** - `test_market_scanner.py`
- **Issue**: Mock object needs proper list return value
- **Fix Required**: `mock_client.get_all_active_markets.return_value = []` (empty list, not Mock)

**6. Position Validator Test (1 failure)** - `test_position_validator.py`
- **Issue**: Mock for token recovery not properly configured
- **Fix Required**: Update mock to return dict instead of Mock object:
  ```python
  self.mock_client.get_market.return_value = {
      'yes_token_id': "0xrecovered123"
  }
  ```

### Migration Path

To update the test suite to match refactored code:

1. **Immediate** (High Priority):
   - Fix `test_position_validator.py::test_validate_token_id_invalid_int` (1 test)
   - Update `test_sell_monitor.py` state structure (9 tests)
   - Update `test_integration.py` mock client (5 tests)

2. **Short Term** (Medium Priority):
   - Update `test_pricing.py` to threshold-based config (3 tests)
   - Fix `test_buy_monitor.py` wei conversion (1 test)
   - Fix `test_market_scanner.py` mock (1 test)

3. **Future** (Low Priority):
   - Add comprehensive tests for new handlers:
     - `test_buy_handler.py` ⭐ NEW
     - `test_sell_handler.py` ⭐ NEW
     - `test_market_selector.py` ⭐ NEW
   - Add tests for `position_recovery.py` ⭐ NEW

### Running Only Passing Tests

To run only currently passing tests:

```bash
# Run specific passing test files
python -m pytest tests/test_autonomous_bot.py tests/test_capital_manager.py tests/test_liquidity_checker.py tests/test_scoring.py tests/test_state_manager.py

# Run with coverage on passing tests only
python -m pytest tests/test_position_validator.py --cov=core/position_validator.py --cov-report=term-missing
```

### Contributing Test Fixes

When updating tests, ensure:
1. Tests match current handler architecture (delegation pattern)
2. State structure matches `bot.state['current_position']` format
3. Mocks implement current API client interface
4. Configuration uses current threshold-based pricing
5. All new tests include docstrings explaining scenario/expected behavior
