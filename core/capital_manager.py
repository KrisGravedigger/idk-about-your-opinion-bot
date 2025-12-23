"""
Capital Manager Module
======================

Manages position sizing based on available balance and configuration.

Key responsibilities:
- Query USDT balance via API
- Calculate position size based on capital mode (fixed/percentage)
- Validate position meets platform constraints
- Warn if position doesn't qualify for airdrop points

Usage:
    from core.capital_manager import CapitalManager
    
    manager = CapitalManager(config, client)
    position_size = manager.get_position_size()
"""

from typing import Dict, Any
from logger_config import setup_logger
from utils import format_usdt

logger = setup_logger(__name__)


class InsufficientCapitalError(Exception):
    """Raised when balance is too low to continue trading."""
    pass


class PositionTooSmallError(Exception):
    """Raised when calculated position size is below platform minimum."""
    pass


class CapitalManager:
    """
    Manages capital allocation and position sizing.
    
    Attributes:
        config: Configuration dictionary
        client: API client instance
    """
    
    def __init__(self, config: Dict[str, Any], client):
        """
        Initialize Capital Manager.
        
        Args:
            config: Configuration dictionary with capital parameters
            client: OpinionClient instance (must have get_usdt_balance method)
        
        Example:
            >>> from config import (CAPITAL_MODE, CAPITAL_AMOUNT_USDT, ...)
            >>> config = {
            ...     'CAPITAL_MODE': 'percentage',
            ...     'CAPITAL_AMOUNT_USDT': 10.0,
            ...     # ... other params ...
            ... }
            >>> manager = CapitalManager(config, client)
        """
        self.config = config
        self.client = client
        
        # Extract config values
        self.capital_mode = config['CAPITAL_MODE']
        self.capital_amount = config['CAPITAL_AMOUNT_USDT']
        self.capital_percentage = config['CAPITAL_PERCENTAGE']
        self.min_balance = config['MIN_BALANCE_TO_CONTINUE_USDT']
        self.min_position = config['MIN_POSITION_SIZE_USDT']
        self.min_for_points = config['MIN_POSITION_FOR_POINTS_USDT']
        self.warn_points = config['WARN_IF_BELOW_POINTS_THRESHOLD']
        
        logger.debug(f"CapitalManager initialized: mode={self.capital_mode}")
    
    def get_position_size(self) -> float:
        """
        Calculate position size based on current balance and capital mode.
        
        Returns:
            Position size in USDT
            
        Raises:
            InsufficientCapitalError: If balance < MIN_BALANCE_TO_CONTINUE_USDT
            PositionTooSmallError: If calculated position < MIN_POSITION_SIZE_USDT
            
        Example:
            >>> # Fixed mode with balance=12, fixed=10
            >>> manager.get_position_size()
            10.0
            
            >>> # Percentage mode with balance=15, percentage=100
            >>> manager.get_position_size()
            15.0
        """
        # Query current USDT balance
        logger.debug("Querying USDT balance from API...")
        balance = self.client.get_usdt_balance()
        logger.info(f"Current USDT balance: {format_usdt(balance)}")
        
        # Check if balance meets minimum threshold
        if balance < self.min_balance:
            error_msg = (
                f"Insufficient balance: {format_usdt(balance)} "
                f"(minimum required: {format_usdt(self.min_balance)})"
            )
            logger.error(f"❌ {error_msg}")
            raise InsufficientCapitalError(error_msg)
        
        # Calculate position size based on mode
        if self.capital_mode == 'fixed':
            position_size = self.capital_amount
            logger.debug(
                f"Fixed mode: position_size = {format_usdt(position_size)}"
            )
        elif self.capital_mode == 'percentage':
            position_size = balance * (self.capital_percentage / 100.0)
            logger.debug(
                f"Percentage mode: {self.capital_percentage}% of "
                f"{format_usdt(balance)} = {format_usdt(position_size)}"
            )
        else:
            raise ValueError(
                f"Invalid CAPITAL_MODE: '{self.capital_mode}' "
                f"(must be 'fixed' or 'percentage')"
            )
        
        # Validate position meets platform minimum
        if position_size < self.min_position:
            error_msg = (
                f"Position size too small: {format_usdt(position_size)} "
                f"(platform minimum: {format_usdt(self.min_position)})"
            )
            logger.error(f"❌ {error_msg}")
            raise PositionTooSmallError(error_msg)
        
        # Warn if position won't earn airdrop points
        if self.warn_points and position_size < self.min_for_points:
            logger.warning(
                f"⚠️  Position {format_usdt(position_size)} is below "
                f"{format_usdt(self.min_for_points)} - will NOT earn airdrop points"
            )
            logger.warning(
                f"   Increase CAPITAL_PERCENTAGE or switch to 'fixed' mode "
                f"with CAPITAL_AMOUNT_USDT >= 10"
            )
        
        logger.info(f"✅ Position size calculated: {format_usdt(position_size)}")
        return position_size


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("Use test_capital_manager.py for comprehensive testing")