#!/usr/bin/env python3
"""
Test State Manager Module
==========================

Comprehensive tests for StateManager with file I/O.

Run with: python test_state_manager.py
"""

import sys
import json
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import after path setup
from core.state_manager import StateManager


def test_1_initialize_new_state():
    """
    Test 1: Initialize new state structure.
    
    Expected:
        - All required fields present
        - Version is '1.0'
        - Stage is 'IDLE'
        - Statistics initialized to zeros
        - Position fields are None
    """
    print("Test 1: Initialize new state")
    
    manager = StateManager(state_file="test_state_1.json")
    state = manager.initialize_state()
    
    # Check top-level fields
    assert state['version'] == '1.0', "Version should be 1.0"
    assert state['stage'] == 'IDLE', "Initial stage should be IDLE"
    assert state['cycle_number'] == 0, "Initial cycle should be 0"
    assert 'started_at' in state, "Should have started_at timestamp"
    assert 'last_updated_at' in state, "Should have last_updated_at timestamp"
    
    # Check statistics
    stats = state['statistics']
    assert stats['total_trades'] == 0, "Initial trades should be 0"
    assert stats['wins'] == 0, "Initial wins should be 0"
    assert stats['losses'] == 0, "Initial losses should be 0"
    assert stats['total_pnl_usdt'] == 0.0, "Initial PnL should be 0.0"
    
    # Check position
    pos = state['current_position']
    assert pos['market_id'] is None, "Initial market_id should be None"
    assert pos['buy_order_id'] is None, "Initial buy_order_id should be None"
    
    print("   ✓ State structure correct")
    print(f"   ✓ Version: {state['version']}")
    print(f"   ✓ Stage: {state['stage']}")
    print()


def test_2_save_and_load_state():
    """
    Test 2: Save state to file and load it back.
    
    Expected:
        - File created successfully
        - Loaded state matches saved state
        - JSON is formatted (pretty printed)
    """
    print("Test 2: Save and load state")
    
    test_file = "test_state_2.json"
    manager = StateManager(state_file=test_file)
    
    # Create and save state
    state = manager.initialize_state()
    state['stage'] = 'BUY_PLACED'
    state['cycle_number'] = 3
    
    success = manager.save_state(state)
    assert success, "Save should succeed"
    
    # Verify file exists
    assert Path(test_file).exists(), f"File {test_file} should exist"
    
    # Load state back
    loaded_state = manager.load_state()
    
    # Compare
    assert loaded_state['version'] == state['version'], "Version mismatch"
    assert loaded_state['stage'] == 'BUY_PLACED', "Stage should be BUY_PLACED"
    assert loaded_state['cycle_number'] == 3, "Cycle should be 3"
    
    print("   ✓ State saved successfully")
    print("   ✓ State loaded successfully")
    print(f"   ✓ Stage: {loaded_state['stage']}")
    print(f"   ✓ Cycle: {loaded_state['cycle_number']}")
    
    # Cleanup
    Path(test_file).unlink()
    print()


def test_3_validate_state_structure():
    """
    Test 3: Validate state structure.
    
    Scenarios:
        a) Valid state should pass
        b) Missing required field should fail
        c) Missing statistics field should fail
    """
    print("Test 3: Validate state structure")
    
    manager = StateManager()
    
    # Test a: Valid state
    valid_state = manager.initialize_state()
    is_valid, errors = manager.validate_state(valid_state)
    assert is_valid, f"Valid state should pass validation: {errors}"
    print("   ✓ Valid state passed")
    
    # Test b: Missing top-level field
    invalid_state = valid_state.copy()
    del invalid_state['stage']
    is_valid, errors = manager.validate_state(invalid_state)
    assert not is_valid, "Should fail with missing 'stage'"
    assert 'stage' in str(errors), "Error should mention 'stage'"
    print("   ✓ Detected missing 'stage' field")
    
    # Test c: Missing statistics field
    invalid_state = manager.initialize_state()
    del invalid_state['statistics']['total_trades']
    is_valid, errors = manager.validate_state(invalid_state)
    assert not is_valid, "Should fail with missing statistics field"
    assert 'total_trades' in str(errors), "Error should mention 'total_trades'"
    print("   ✓ Detected missing statistics field")
    print()


def test_4_reset_position():
    """
    Test 4: Reset position while preserving statistics.
    
    Expected:
        - All position fields set to None
        - Stage changed to IDLE
        - Statistics unchanged
    """
    print("Test 4: Reset position (preserve statistics)")
    
    manager = StateManager()
    state = manager.initialize_state()
    
    # Simulate filled position with stats
    state['stage'] = 'SELL_MONITORING'
    state['current_position']['market_id'] = 813
    state['current_position']['buy_order_id'] = 'ord_123'
    state['statistics']['total_trades'] = 5
    state['statistics']['wins'] = 3
    state['statistics']['total_pnl_usdt'] = 12.50
    
    # Reset position
    state = manager.reset_position(state)
    
    # Check position cleared
    assert state['stage'] == 'IDLE', "Stage should be IDLE"
    assert state['current_position']['market_id'] is None, "market_id should be None"
    assert state['current_position']['buy_order_id'] is None, "buy_order_id should be None"
    
    # Check statistics preserved
    assert state['statistics']['total_trades'] == 5, "total_trades should be preserved"
    assert state['statistics']['wins'] == 3, "wins should be preserved"
    assert state['statistics']['total_pnl_usdt'] == 12.50, "PnL should be preserved"
    
    print("   ✓ Position cleared")
    print("   ✓ Statistics preserved")
    print(f"   ✓ Stage: {state['stage']}")
    print(f"   ✓ Total trades: {state['statistics']['total_trades']}")
    print()


def test_5_migration_from_v0():
    """
    Test 5: Migrate from old state format.
    
    Old format had stage names like 'stage2_scanning'.
    New format uses simple names like 'SCANNING'.
    
    Expected:
        - Old stage mapped to new stage
        - Statistics preserved
        - Version updated to '1.0'
    """
    print("Test 5: Migration from old state format")
    
    test_file = "test_state_5_old.json"
    
    # Create old format state
    old_state = {
        "stage": "stage3_buy_monitoring",
        "cycle_number": 2,
        "statistics": {
            "total_trades": 3,
            "wins": 2,
            "losses": 1,
            "consecutive_losses": 0,
            "total_pnl_usdt": 5.75,
            "total_pnl_percent": 2.5,
            "win_rate_percent": 66.67
        },
        "current_position": {
            "market_id": 813,
            "buy_order_id": "ord_456"
        }
    }
    
    # Save old format
    with open(test_file, 'w') as f:
        json.dump(old_state, f)
    
    # Load with StateManager (should trigger migration)
    manager = StateManager(state_file=test_file)
    migrated_state = manager.load_state()
    
    # Check migration results
    assert migrated_state['version'] == '1.0', "Version should be updated"
    assert migrated_state['stage'] == 'BUY_MONITORING', "Stage should be mapped"
    assert migrated_state['cycle_number'] == 2, "Cycle should be preserved"
    assert migrated_state['statistics']['total_trades'] == 3, "Stats should be preserved"
    assert migrated_state['statistics']['wins'] == 2, "Wins should be preserved"
    assert migrated_state['current_position']['market_id'] == 813, "Position preserved"
    
    print("   ✓ Migration successful")
    print(f"   ✓ Old stage: stage3_buy_monitoring")
    print(f"   ✓ New stage: {migrated_state['stage']}")
    print(f"   ✓ Statistics preserved: {migrated_state['statistics']['total_trades']} trades")
    
    # Cleanup
    Path(test_file).unlink()
    print()


def test_6_roundtrip_with_validation():
    """
    Test 6: Complete roundtrip - initialize → save → load → validate.
    
    Expected:
        - Full cycle works without errors
        - Validation passes after roundtrip
    """
    print("Test 6: Complete roundtrip with validation")
    
    test_file = "test_state_6.json"
    manager = StateManager(state_file=test_file)
    
    # Initialize
    state = manager.initialize_state()
    print("   ✓ State initialized")
    
    # Validate initial
    is_valid, errors = manager.validate_state(state)
    assert is_valid, f"Initial state should be valid: {errors}"
    print("   ✓ Initial validation passed")
    
    # Save
    success = manager.save_state(state)
    assert success, "Save should succeed"
    print("   ✓ State saved")
    
    # Load
    loaded_state = manager.load_state()
    print("   ✓ State loaded")
    
    # Validate loaded
    is_valid, errors = manager.validate_state(loaded_state)
    assert is_valid, f"Loaded state should be valid: {errors}"
    print("   ✓ Final validation passed")
    
    # Cleanup
    Path(test_file).unlink()
    print()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("STATE MANAGER TESTS")
    print("=" * 60)
    print()
    
    try:
        test_1_initialize_new_state()
        test_2_save_and_load_state()
        test_3_validate_state_structure()
        test_4_reset_position()
        test_5_migration_from_v0()
        test_6_roundtrip_with_validation()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
        # Cleanup any remaining test files
        for test_file in Path('.').glob('test_state_*.json'):
            test_file.unlink()
            print(f"   Cleaned up: {test_file}")
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ UNEXPECTED ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)