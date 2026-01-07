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
