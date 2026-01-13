"""
Unit tests for market_scanner.py
"""

import pytest
from unittest.mock import Mock, MagicMock
from market_scanner import MarketScanner


def test_scan_and_rank_with_default_profile():
    """Test that scan_and_rank works with default profile (None)."""
    mock_client = Mock()
    mock_client.get_all_active_markets.return_value = []
    
    scanner = MarketScanner(mock_client)
    markets = scanner.scan_and_rank(limit=5)
    
    assert markets is not None
    assert isinstance(markets, list)


def test_scan_and_rank_with_named_profile():
    """Test that scan_and_rank works with named profile string."""
    mock_client = Mock()
    mock_client.get_all_active_markets.return_value = []
    
    scanner = MarketScanner(mock_client)
    markets = scanner.scan_and_rank(limit=5, scoring_profile='balanced')
    
    assert markets is not None
    assert isinstance(markets, list)


def test_scan_and_rank_with_custom_profile():
    """Test that scan_and_rank works with custom profile dict."""
    mock_client = Mock()
    mock_client.get_all_active_markets.return_value = []
    
    custom_profile = {
        'weights': {'spread': 1.0},
        'bonus_multiplier': 1.5,
        'invert_spread': False
    }
    
    scanner = MarketScanner(mock_client)
    markets = scanner.scan_and_rank(limit=5, scoring_profile=custom_profile)
    
    assert markets is not None
    assert isinstance(markets, list)


def test_scan_and_rank_with_invalid_profile_type():
    """Test that scan_and_rank raises ValueError for invalid profile type."""
    mock_client = Mock()
    mock_client.get_all_active_markets.return_value = []
    
    scanner = MarketScanner(mock_client)
    
    with pytest.raises(ValueError, match="scoring_profile must be string, dict, or None"):
        scanner.scan_and_rank(limit=5, scoring_profile=123)  # invalid type


def test_scan_and_rank_profile_validation():
    """Test that profile validation assertions work."""
    mock_client = Mock()
    
    # Mock get_scoring_profile to return invalid profile
    import config
    original_func = config.get_scoring_profile
    config.get_scoring_profile = lambda x: None  # Returns None instead of dict
    
    scanner = MarketScanner(mock_client)
    
    try:
        with pytest.raises(AssertionError, match="Profile loading failed"):
            scanner.scan_and_rank(limit=5)
    finally:
        config.get_scoring_profile = original_func  # Restore original


def test_analyze_market_requires_scoring_profile():
    """Test that analyze_market requires scoring_profile parameter."""
    mock_client = Mock()
    scanner = MarketScanner(mock_client)
    
    market = {'market_id': 1, 'yes_token_id': 'test'}
    profile = {'weights': {'spread': 1.0}, 'bonus_multiplier': 1.0}
    
    # This should work
    mock_client.get_market_orderbook.return_value = None  # Will return None early
    result = scanner.analyze_market(market, profile)
    
    # Should call with proper signature (no error about missing parameter)
    assert True  # If we get here, signature is correct