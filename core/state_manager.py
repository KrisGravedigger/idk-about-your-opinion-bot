"""
State Manager Module
====================

Manages bot state persistence and statistics tracking.

Key responsibilities:
- Load/save state.json with bot progress and statistics
- Initialize fresh state with proper structure
- Validate state integrity
- Reset position while preserving statistics
- Migrate from old state format (v0 -> v1)

Usage:
    from core.state_manager import StateManager
    
    manager = StateManager()
    state = manager.load_state()
    manager.save_state(state)
"""

import json
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from logger_config import setup_logger
from utils import get_timestamp

logger = setup_logger(__name__)


class StateManager:
    """
    Manages bot state persistence and validation.
    
    Attributes:
        state_file: Path to state.json file
    """
    
    def __init__(self, state_file: str = "state.json"):
        """
        Initialize State Manager.
        
        Args:
            state_file: Path to state file (default: state.json)
            
        Example:
            >>> manager = StateManager()
            >>> manager = StateManager("custom_state.json")
        """
        self.state_file = Path(state_file)
        logger.debug(f"StateManager initialized: {self.state_file}")
    
    def load_state(self) -> Dict[str, Any]:
        """
        Load state from file, return default if missing.
        
        Returns:
            State dictionary
            
        Example:
            >>> manager = StateManager()
            >>> state = manager.load_state()
            >>> print(state['stage'])
            'IDLE'
        """
        if not self.state_file.exists():
            logger.info("No state file found, initializing fresh state")
            return self.initialize_state()
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            logger.info(f"✅ State loaded from {self.state_file}")
            logger.debug(f"   Stage: {state.get('stage', 'UNKNOWN')}")
            logger.debug(f"   Cycle: {state.get('cycle_number', 0)}")
            
            # Check if migration needed
            if state.get('version') != '1.0':
                logger.info("Migrating state from old format...")
                state = self._migrate_from_v0(state)
                self.save_state(state)
            
            return state
            
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading state file: {e}")
            logger.warning("Initializing fresh state")
            return self.initialize_state()
    
    def save_state(self, state: Dict[str, Any]) -> bool:
        """
        Save state to file with pretty JSON formatting.
        
        Args:
            state: State dictionary to save
            
        Returns:
            True if saved successfully, False otherwise
            
        Example:
            >>> state = {'stage': 'BUY_PLACED', 'order_id': 'ord_123'}
            >>> manager.save_state(state)
            True
        """
        try:
            # Update timestamp
            state['last_updated_at'] = get_timestamp()
            
            # Save with pretty formatting
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"State saved to {self.state_file}")
            return True
            
        except IOError as e:
            logger.error(f"Error saving state: {e}")
            return False
    
    def initialize_state(self) -> Dict[str, Any]:
        """
        Create fresh state with proper structure.
        
        Returns:
            New state dictionary with default values
            
        Example:
            >>> manager = StateManager()
            >>> state = manager.initialize_state()
            >>> state['version']
            '1.0'
        """
        timestamp = get_timestamp()
        
        state = {
            "version": "1.0",
            "stage": "IDLE",
            "cycle_number": 0,
            "started_at": timestamp,
            "last_updated_at": timestamp,
            
            "statistics": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "consecutive_losses": 0,
                "total_pnl_usdt": 0.0,
                "total_pnl_percent": 0.0,
                "win_rate_percent": 0.0
            },
            
            "current_position": {
                "market_id": None,
                "token_id": None,
                "market_title": None,
                "buy_order_id": None,
                "buy_amount_usdt": None,
                "buy_tokens": None,
                "buy_price": None,
                "buy_filled_at": None,
                "sell_order_id": None,
                "sell_amount_usdt": None,
                "sell_tokens": None,
                "sell_price": None,
                "sell_filled_at": None,
                "pnl_usdt": None,
                "pnl_percent": None
            }
        }
        
        logger.info("✅ Fresh state initialized")
        return state
    
    def validate_state(self, state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate state structure and required fields.
        
        Args:
            state: State dictionary to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
            
        Example:
            >>> manager = StateManager()
            >>> state = manager.initialize_state()
            >>> is_valid, errors = manager.validate_state(state)
            >>> is_valid
            True
        """
        errors = []
        
        # Check top-level required fields
        required_top = ['version', 'stage', 'cycle_number', 'statistics', 'current_position']
        for field in required_top:
            if field not in state:
                errors.append(f"Missing required field: {field}")
        
        # Check statistics structure
        if 'statistics' in state:
            required_stats = [
                'total_trades', 'wins', 'losses', 'consecutive_losses',
                'total_pnl_usdt', 'total_pnl_percent', 'win_rate_percent'
            ]
            for field in required_stats:
                if field not in state['statistics']:
                    errors.append(f"Missing statistics field: {field}")
        
        # Check current_position structure
        if 'current_position' in state:
            required_position = [
                'market_id', 'token_id', 'market_title',
                'buy_order_id', 'buy_amount_usdt', 'buy_tokens', 'buy_price',
                'sell_order_id', 'sell_amount_usdt', 'sell_tokens', 'sell_price'
            ]
            for field in required_position:
                if field not in state['current_position']:
                    errors.append(f"Missing position field: {field}")
        
        is_valid = len(errors) == 0
        
        if is_valid:
            logger.debug("✅ State validation passed")
        else:
            logger.error(f"❌ State validation failed: {len(errors)} errors")
            for error in errors:
                logger.error(f"   - {error}")
        
        return (is_valid, errors)
    
    def reset_position(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clear position data while preserving statistics.
        
        Args:
            state: Current state dictionary
            
        Returns:
            Updated state with cleared position
            
        Example:
            >>> state['current_position']['market_id'] = 813
            >>> state = manager.reset_position(state)
            >>> state['current_position']['market_id']
            None
        """
        # Reset all position fields to None
        state['current_position'] = {
            "market_id": None,
            "token_id": None,
            "market_title": None,
            "buy_order_id": None,
            "buy_amount_usdt": None,
            "buy_tokens": None,
            "buy_price": None,
            "buy_filled_at": None,
            "sell_order_id": None,
            "sell_amount_usdt": None,
            "sell_tokens": None,
            "sell_price": None,
            "sell_filled_at": None,
            "pnl_usdt": None,
            "pnl_percent": None
        }
        
        # Set stage to IDLE
        state['stage'] = 'IDLE'
        
        logger.debug("Position reset, statistics preserved")
        return state
    
    def _migrate_from_v0(self, old_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate old state format to v1.0.
        
        Old format used 'stage' field with values like:
        - 'stage2_scanning'
        - 'stage3_buy_monitoring'
        - 'stage4_sell_monitoring'
        
        New format uses simplified stage names:
        - 'IDLE'
        - 'SCANNING'
        - 'BUY_PLACED'
        - 'BUY_MONITORING'
        - 'SELL_PLACED'
        - 'SELL_MONITORING'
        
        Args:
            old_state: State in old format
            
        Returns:
            State in v1.0 format
        """
        logger.info("Migrating state from v0 to v1.0...")
        
        # Initialize new state structure
        new_state = self.initialize_state()
        
        # Map old stage names to new
        stage_mapping = {
            'stage2_scanning': 'SCANNING',
            'stage2_order_placed': 'BUY_PLACED',
            'stage3_buy_monitoring': 'BUY_MONITORING',
            'stage4_sell_placed': 'SELL_PLACED',
            'stage4_sell_monitoring': 'SELL_MONITORING',
            'completed': 'IDLE',
            'initial': 'IDLE'
        }
        
        old_stage = old_state.get('stage', 'initial')
        new_state['stage'] = stage_mapping.get(old_stage, 'IDLE')
        
        # Preserve cycle number if present
        if 'cycle_number' in old_state:
            new_state['cycle_number'] = old_state['cycle_number']
        
        # Preserve timestamps if present
        if 'started_at' in old_state:
            new_state['started_at'] = old_state['started_at']
        
        # Preserve statistics if present
        if 'statistics' in old_state:
            old_stats = old_state['statistics']
            new_stats = new_state['statistics']
            
            # Copy fields that exist
            for field in new_stats.keys():
                if field in old_stats:
                    new_stats[field] = old_stats[field]
        
        # Preserve position data if present
        if 'current_position' in old_state or 'position' in old_state:
            old_pos = old_state.get('current_position', old_state.get('position', {}))
            new_pos = new_state['current_position']
            
            # Copy fields that exist
            for field in new_pos.keys():
                if field in old_pos:
                    new_pos[field] = old_pos[field]
        
        logger.info(f"✅ Migration complete: {old_stage} → {new_state['stage']}")
        return new_state


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("Use test_state_manager.py for comprehensive testing")