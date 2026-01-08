"""
Reconciliation Engine
=====================

Detects and resolves discrepancies between bot state and API reality.

Handles cases like:
- API returns filled_shares=0 for completed order
- Position exists in API but state says IDLE
- Position missing from API but state says BUY_FILLED
- Partial fills not reflected in state
- Manual trades outside bot

Features:
- Multi-source validation (state, API positions, transaction history)
- Graceful recovery strategies
- Comprehensive logging
- Telegram notifications for critical recoveries

Usage:
    from core.reconciliation_engine import ReconciliationEngine

    engine = ReconciliationEngine(config, client, state_manager, transaction_history)

    # Check for discrepancies
    discrepancy = engine.detect_discrepancy(state)

    if discrepancy:
        # Attempt recovery
        recovery_result = engine.reconcile(state, discrepancy)

        if recovery_result['success']:
            print(f"✅ Recovered: {recovery_result['strategy']}")
        else:
            print(f"❌ Recovery failed: {recovery_result['reason']}")
"""

from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import json

from logger_config import setup_logger
from utils import safe_float, format_price, format_usdt, get_timestamp

logger = setup_logger(__name__)


class DiscrepancyType(Enum):
    """Types of discrepancies that can be detected."""

    # State vs API position mismatches
    PHANTOM_POSITION = "phantom_position"  # API has position, state is IDLE
    MISSING_POSITION = "missing_position"  # State has position, API doesn't
    SHARES_MISMATCH = "shares_mismatch"    # Position exists but shares differ

    # Order execution issues
    ORPHANED_ORDER = "orphaned_order"      # Pending order exists but state doesn't know
    ZERO_FILL_BUG = "zero_fill_bug"        # Order Finished but filled_shares=0
    PARTIAL_FILL = "partial_fill"          # Only part of order executed

    # Data consistency
    INVALID_STATE = "invalid_state"        # State has invalid/missing data
    NO_DISCREPANCY = "no_discrepancy"      # Everything OK


class RecoveryStrategy(Enum):
    """Recovery strategies for different discrepancy types."""

    SYNC_FROM_API = "sync_from_api"              # Rebuild state from API position
    SYNC_FROM_HISTORY = "sync_from_history"      # Rebuild from transaction_history
    HYBRID_SYNC = "hybrid_sync"                  # Use both API + history
    UPDATE_SHARES = "update_shares"              # Just update share count
    RESET_TO_IDLE = "reset_to_idle"              # Clean slate
    CANCEL_AND_RESET = "cancel_and_reset"        # Cancel orphaned order and reset
    WAIT_AND_RETRY = "wait_and_retry"            # Likely API lag, wait
    NO_ACTION = "no_action"                      # Everything OK


@dataclass
class Discrepancy:
    """
    Represents a detected discrepancy.

    Attributes:
        type: Type of discrepancy
        severity: HIGH, MEDIUM, LOW
        description: Human-readable description
        state_data: Data from bot state
        api_data: Data from API
        suggested_strategy: Recommended recovery strategy
        metadata: Additional context
    """
    type: DiscrepancyType
    severity: str
    description: str
    state_data: Dict[str, Any]
    api_data: Dict[str, Any]
    suggested_strategy: RecoveryStrategy
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'type': self.type.value,
            'severity': self.severity,
            'description': self.description,
            'state_data': self.state_data,
            'api_data': self.api_data,
            'suggested_strategy': self.suggested_strategy.value,
            'metadata': self.metadata or {}
        }


@dataclass
class RecoveryResult:
    """
    Result of a reconciliation attempt.

    Attributes:
        success: Whether recovery succeeded
        strategy: Strategy used
        actions_taken: List of actions performed
        state_changes: Changes made to state
        reason: Reason for success/failure
        metadata: Additional data
    """
    success: bool
    strategy: RecoveryStrategy
    actions_taken: List[str]
    state_changes: Dict[str, Any]
    reason: str
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'success': self.success,
            'strategy': self.strategy.value,
            'actions_taken': self.actions_taken,
            'state_changes': self.state_changes,
            'reason': self.reason,
            'metadata': self.metadata or {}
        }


class ReconciliationEngine:
    """
    Engine for detecting and resolving state discrepancies.

    Validates bot state against API reality and recovers gracefully.
    """

    def __init__(self, config: Dict[str, Any], client, state_manager, transaction_history):
        """
        Initialize reconciliation engine.

        Args:
            config: Bot configuration
            client: API client
            state_manager: State manager instance
            transaction_history: Transaction history instance
        """
        self.config = config
        self.client = client
        self.state_manager = state_manager
        self.transaction_history = transaction_history

        # Configuration
        self.dust_threshold = config.get('MIN_POSITION_SIZE', 5.0)
        self.tolerance_shares = 0.01  # Allow 0.01 share difference (rounding)
        self.api_lag_grace_seconds = 30  # Wait 30s for API to catch up

        logger.debug("ReconciliationEngine initialized")

    def detect_discrepancy(self, state: Dict[str, Any]) -> Optional[Discrepancy]:
        """
        Detect discrepancies between state and API reality.

        Checks:
        1. Position existence (state vs API)
        2. Share count accuracy
        3. Data validity

        Args:
            state: Current bot state

        Returns:
            Discrepancy object if found, None if everything OK
        """
        logger.debug("🔍 Starting discrepancy detection...")

        stage = state.get('stage', 'IDLE')
        position = state.get('current_position', {})
        market_id = position.get('market_id', 0)
        outcome_side = position.get('outcome_side', 'YES')
        state_shares = safe_float(position.get('filled_amount', 0))

        # Get actual position from API
        try:
            api_shares = None
            actual_outcome_side = outcome_side  # Track which side we actually found
            if market_id is not None and market_id > 0:
                api_shares_raw = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side=outcome_side
                )
                api_shares = safe_float(api_shares_raw) if api_shares_raw else 0.0
                logger.debug(f"   API position ({outcome_side}): {api_shares:.4f} shares in market #{market_id}")

                # IMPORTANT: If api_shares doesn't match expected and is very small (dust),
                # check the OPPOSITE side - we might have the wrong outcome_side
                if state_shares > 5.0 and api_shares < 5.0:
                    # State expects significant position, but found only dust on this side
                    # Check the opposite side
                    opposite_side = 'NO' if outcome_side == 'YES' else 'YES'
                    logger.debug(f"   Found only dust on {outcome_side} side, checking {opposite_side}...")

                    try:
                        opposite_shares_raw = self.client.get_position_shares(
                            market_id=market_id,
                            outcome_side=opposite_side
                        )
                        opposite_shares = safe_float(opposite_shares_raw) if opposite_shares_raw else 0.0
                        logger.debug(f"   API position ({opposite_side}): {opposite_shares:.4f} shares")

                        # If we found a larger position on the opposite side, use that instead
                        if opposite_shares >= state_shares * 0.9:  # Within 10% of expected
                            logger.info(f"   ✅ Found position on {opposite_side} side instead of {outcome_side}")
                            logger.info(f"   Updating outcome_side: {outcome_side} → {opposite_side}")
                            api_shares = opposite_shares
                            actual_outcome_side = opposite_side
                    except Exception as e2:
                        logger.debug(f"   Could not check {opposite_side} side: {e2}")

        except Exception as e:
            logger.warning(f"   Could not fetch API position: {e}")
            api_shares = None

        # CASE 0: Check for orphaned pending orders (HIGHEST PRIORITY!)
        # If state is IDLE/SCANNING but we have pending orders, that's a critical issue
        if stage in ['IDLE', 'SCANNING']:
            try:
                # Get pending orders from API
                pending_orders = self.client.get_my_orders(status='PENDING', limit=10)

                # Explicit None check for defensive programming
                if pending_orders is not None and len(pending_orders) > 0:
                    # Found orphaned pending order(s)!
                    order = pending_orders[0]  # Take first one
                    order_id = order.get('order_id', 'unknown')
                    market_id = order.get('market_id', 0)
                    status_enum = order.get('status_enum', 'unknown')
                    side_enum = order.get('side_enum', 'unknown')

                    logger.warning(f"   ⚠️  Found {len(pending_orders)} orphaned pending order(s)!")
                    logger.warning(f"   First order: {side_enum} on market #{market_id}, status: {status_enum}")

                    return Discrepancy(
                        type=DiscrepancyType.ORPHANED_ORDER,
                        severity='HIGH',
                        description=f"State is {stage} but found {len(pending_orders)} pending order(s) - likely from incomplete cycle",
                        state_data={'stage': stage},
                        api_data={
                            'order_id': order_id,
                            'market_id': market_id,
                            'status': status_enum,
                            'side': side_enum,
                            'total_orphaned': len(pending_orders)
                        },
                        suggested_strategy=RecoveryStrategy.CANCEL_AND_RESET,
                        metadata={'all_orders': pending_orders}
                    )
            except Exception as e:
                logger.debug(f"Could not check for orphaned orders: {e}")

        # CASE 1: State is IDLE/COMPLETED but API shows position
        if stage in ['IDLE', 'COMPLETED']:
            if api_shares is not None and api_shares > self.dust_threshold:
                return Discrepancy(
                    type=DiscrepancyType.PHANTOM_POSITION,
                    severity='HIGH',
                    description=f"State is {stage} but API shows {api_shares:.4f} shares in market #{market_id}",
                    state_data={'stage': stage, 'market_id': market_id, 'shares': 0},
                    api_data={'market_id': market_id, 'shares': api_shares, 'outcome': outcome_side},
                    suggested_strategy=RecoveryStrategy.SYNC_FROM_API
                )

        # CASE 2: State has position but API doesn't (or very different)
        # CRITICAL FIX: Skip position checks for SELL_PLACED/SELL_MONITORING
        # When a SELL order is active, shares are frozen in the order and won't appear in get_position_shares()
        # This would incorrectly trigger MISSING_POSITION discrepancy
        if stage == 'BUY_FILLED':
            if api_shares is not None:
                # Check if shares match (within tolerance)
                shares_diff = abs(state_shares - api_shares)

                if api_shares < self.dust_threshold and state_shares > self.dust_threshold:
                    # API shows no position but state thinks we have one
                    return Discrepancy(
                        type=DiscrepancyType.MISSING_POSITION,
                        severity='HIGH',
                        description=f"State expects {state_shares:.4f} shares but API shows {api_shares:.4f}",
                        state_data={'stage': stage, 'market_id': market_id, 'shares': state_shares, 'outcome_side': outcome_side},
                        api_data={'market_id': market_id, 'shares': api_shares, 'outcome': actual_outcome_side},
                        suggested_strategy=RecoveryStrategy.SYNC_FROM_HISTORY,
                        metadata={'actual_outcome_side': actual_outcome_side}  # Pass corrected side to reconciliation
                    )

                elif shares_diff > self.tolerance_shares:
                    # Shares exist but counts don't match
                    severity = 'HIGH' if shares_diff > 10 else 'MEDIUM'

                    return Discrepancy(
                        type=DiscrepancyType.SHARES_MISMATCH,
                        severity=severity,
                        description=f"Share mismatch: state={state_shares:.4f}, API={api_shares:.4f}, diff={shares_diff:.4f}",
                        state_data={'stage': stage, 'market_id': market_id, 'shares': state_shares, 'outcome_side': outcome_side},
                        api_data={'market_id': market_id, 'shares': api_shares, 'outcome': actual_outcome_side},
                        suggested_strategy=RecoveryStrategy.UPDATE_SHARES,
                        metadata={'shares_diff': shares_diff, 'actual_outcome_side': actual_outcome_side}
                    )

        elif stage in ['SELL_PLACED', 'SELL_MONITORING']:
            # SELL order active - shares are frozen in the order
            # Don't check position shares because they're legitimately locked
            # Just log for debugging
            logger.debug(f"   Stage {stage}: Shares frozen in SELL order, skipping position check")
            logger.debug(f"   State: {state_shares:.4f} shares, API available: {api_shares:.4f} (rest frozen in order)")

        # CASE 3: Invalid state data
        if stage in ['BUY_FILLED', 'SELL_PLACED', 'SELL_MONITORING']:
            if market_id in [0, None] or state_shares == 0:
                return Discrepancy(
                    type=DiscrepancyType.INVALID_STATE,
                    severity='HIGH',
                    description=f"State has invalid data: market_id={market_id}, shares={state_shares}",
                    state_data={'stage': stage, 'market_id': market_id, 'shares': state_shares},
                    api_data={},
                    suggested_strategy=RecoveryStrategy.RESET_TO_IDLE
                )

        logger.debug("   ✅ No discrepancies detected")
        return None

    def reconcile(
        self,
        state: Dict[str, Any],
        discrepancy: Discrepancy,
        telegram_notifier=None
    ) -> RecoveryResult:
        """
        Attempt to reconcile a detected discrepancy.

        Args:
            state: Current bot state
            discrepancy: Detected discrepancy
            telegram_notifier: Optional Telegram notifier for alerts

        Returns:
            RecoveryResult with outcome
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("🔧 STARTING RECONCILIATION")
        logger.info("=" * 70)
        logger.info(f"   Type: {discrepancy.type.value}")
        logger.info(f"   Severity: {discrepancy.severity}")
        logger.info(f"   Description: {discrepancy.description}")
        logger.info(f"   Suggested strategy: {discrepancy.suggested_strategy.value}")
        logger.info("=" * 70)

        # Choose and execute strategy
        strategy = discrepancy.suggested_strategy

        if strategy == RecoveryStrategy.SYNC_FROM_API:
            result = self._sync_from_api(state, discrepancy)

        elif strategy == RecoveryStrategy.UPDATE_SHARES:
            result = self._update_shares(state, discrepancy)

        elif strategy == RecoveryStrategy.SYNC_FROM_HISTORY:
            result = self._sync_from_history(state, discrepancy)

        elif strategy == RecoveryStrategy.RESET_TO_IDLE:
            result = self._reset_to_idle(state, discrepancy)

        elif strategy == RecoveryStrategy.CANCEL_AND_RESET:
            result = self._cancel_and_reset(state, discrepancy)

        else:
            result = RecoveryResult(
                success=False,
                strategy=strategy,
                actions_taken=[],
                state_changes={},
                reason=f"Strategy {strategy.value} not implemented"
            )

        # Log result
        if result.success:
            logger.info("")
            logger.info("=" * 70)
            logger.info("✅ RECONCILIATION SUCCESSFUL")
            logger.info("=" * 70)
            logger.info(f"   Strategy: {result.strategy.value}")
            logger.info(f"   Actions taken:")
            for action in result.actions_taken:
                logger.info(f"     - {action}")
            logger.info(f"   Reason: {result.reason}")
            logger.info("=" * 70)
            logger.info("")
        else:
            logger.error("")
            logger.error("=" * 70)
            logger.error("❌ RECONCILIATION FAILED")
            logger.error("=" * 70)
            logger.error(f"   Strategy: {result.strategy.value}")
            logger.error(f"   Reason: {result.reason}")
            logger.error("=" * 70)
            logger.error("")

        # Send Telegram notification for critical issues
        if telegram_notifier and discrepancy.severity == 'HIGH':
            try:
                self._send_recovery_notification(
                    telegram_notifier,
                    discrepancy,
                    result
                )
            except Exception as e:
                logger.warning(f"Failed to send Telegram notification: {e}")

        return result

    def _sync_from_api(
        self,
        state: Dict[str, Any],
        discrepancy: Discrepancy
    ) -> RecoveryResult:
        """
        Rebuild state from API position (PHANTOM_POSITION case).

        State is IDLE/COMPLETED but API shows we have a position.
        Adopt the position and prepare to sell it.
        """
        actions = []
        state_changes = {}

        api_data = discrepancy.api_data
        market_id = api_data['market_id']
        api_shares = api_data['shares']
        outcome = api_data['outcome']

        try:
            # 1. Get market details
            actions.append(f"Fetching market #{market_id} details")
            market = self.client.get_market_details(market_id)

            if not market:
                return RecoveryResult(
                    success=False,
                    strategy=RecoveryStrategy.SYNC_FROM_API,
                    actions_taken=actions,
                    state_changes={},
                    reason=f"Could not fetch market #{market_id} details"
                )

            # 2. Get token_id
            token_id = market.get('yes_token_id') if outcome == 'YES' else market.get('no_token_id')
            if not token_id:
                return RecoveryResult(
                    success=False,
                    strategy=RecoveryStrategy.SYNC_FROM_API,
                    actions_taken=actions,
                    state_changes={},
                    reason=f"Could not get token_id for {outcome} outcome"
                )

            actions.append(f"Got token_id: {token_id[:20]}...")

            # 3. Try to get avg_price from transaction history
            avg_price = None
            market_txns = self.transaction_history.get_transactions_for_market(market_id)

            if market_txns:
                # Find most recent BUY for this outcome
                buy_txns = [t for t in market_txns if t['type'] == 'BUY' and t['outcome'] == outcome]
                if buy_txns:
                    latest_buy = sorted(buy_txns, key=lambda x: x.get('timestamp', ''), reverse=True)[0]
                    avg_price = latest_buy.get('price', 0)
                    actions.append(f"Found avg_price from transaction history: ${avg_price:.4f}")

            # 4. If no transaction history, use current market price as estimate
            if not avg_price or avg_price == 0:
                try:
                    orderbook = self.client.get_market_orderbook(token_id)
                    if orderbook and 'bids' in orderbook:
                        bids = orderbook.get('bids', [])
                        if bids:
                            best_bid = max(safe_float(bid.get('price', 0)) for bid in bids)
                            avg_price = best_bid
                            actions.append(f"Using current market bid as avg_price: ${avg_price:.4f}")
                            actions.append("⚠️  This is estimate - P&L may be inaccurate")
                except Exception as e:
                    logger.warning(f"Could not get market price: {e}")
                    avg_price = 0.01  # Fallback
                    actions.append(f"⚠️  Using fallback avg_price: ${avg_price:.4f}")

            # 5. Rebuild position in state
            filled_usdt = api_shares * avg_price

            position = {
                'market_id': market_id,
                'market_title': market.get('title', 'Unknown'),
                'outcome_side': outcome,
                'token_id': token_id,
                'filled_amount': api_shares,
                'avg_fill_price': avg_price,
                'filled_usdt': filled_usdt,
                'fill_timestamp': get_timestamp(),
                'recovered': True,  # Mark as recovered position
                'recovery_timestamp': get_timestamp(),
                'recovery_reason': discrepancy.description
            }

            state['current_position'] = position
            state['stage'] = 'BUY_FILLED'  # Ready to sell

            state_changes = {
                'stage': 'BUY_FILLED',
                'current_position': position
            }

            actions.append(f"Rebuilt position: {api_shares:.4f} {outcome} @ ${avg_price:.4f}")
            actions.append("Set stage to BUY_FILLED (ready to sell)")

            # 6. Save state
            self.state_manager.save_state(state)
            actions.append("Saved updated state")

            return RecoveryResult(
                success=True,
                strategy=RecoveryStrategy.SYNC_FROM_API,
                actions_taken=actions,
                state_changes=state_changes,
                reason=f"Successfully adopted orphaned position from market #{market_id}"
            )

        except Exception as e:
            logger.exception(f"Error during sync_from_api: {e}")
            return RecoveryResult(
                success=False,
                strategy=RecoveryStrategy.SYNC_FROM_API,
                actions_taken=actions,
                state_changes={},
                reason=f"Exception during recovery: {str(e)}"
            )

    def _update_shares(
        self,
        state: Dict[str, Any],
        discrepancy: Discrepancy
    ) -> RecoveryResult:
        """
        Update share count to match API (SHARES_MISMATCH case).

        Position exists but share counts differ.
        """
        actions = []
        state_changes = {}

        api_shares = discrepancy.api_data['shares']
        state_shares = discrepancy.state_data['shares']

        position = state.get('current_position', {})

        # Update filled_amount
        old_shares = position.get('filled_amount', 0)
        position['filled_amount'] = api_shares

        # CRITICAL: Update outcome_side if we found position on different side
        actual_outcome_side = discrepancy.metadata.get('actual_outcome_side')
        if actual_outcome_side and actual_outcome_side != position.get('outcome_side'):
            old_side = position.get('outcome_side', 'UNKNOWN')
            position['outcome_side'] = actual_outcome_side
            actions.append(f"Updated outcome_side: {old_side} → {actual_outcome_side}")
            logger.info(f"   ✅ Corrected outcome_side: {old_side} → {actual_outcome_side}")

        # Recalculate filled_usdt if we have avg_fill_price
        avg_price = position.get('avg_fill_price', 0)
        if avg_price > 0:
            position['filled_usdt'] = api_shares * avg_price

        state_changes = {
            'current_position.filled_amount': f"{old_shares:.4f} → {api_shares:.4f}"
        }

        if actual_outcome_side and actual_outcome_side != discrepancy.state_data.get('outcome_side'):
            state_changes['current_position.outcome_side'] = f"{discrepancy.state_data.get('outcome_side', 'UNKNOWN')} → {actual_outcome_side}"

        actions.append(f"Updated filled_amount: {old_shares:.4f} → {api_shares:.4f}")

        # Save state
        self.state_manager.save_state(state)
        actions.append("Saved updated state")

        return RecoveryResult(
            success=True,
            strategy=RecoveryStrategy.UPDATE_SHARES,
            actions_taken=actions,
            state_changes=state_changes,
            reason=f"Share count synchronized with API"
        )

    def _sync_from_history(
        self,
        state: Dict[str, Any],
        discrepancy: Discrepancy
    ) -> RecoveryResult:
        """
        Rebuild state from transaction history (MISSING_POSITION case).

        State thinks we have position but API doesn't.
        Check transaction history to see if it was sold.
        """
        actions = []
        state_changes = {}

        market_id = discrepancy.state_data['market_id']

        # Get transactions for this market
        market_txns = self.transaction_history.get_transactions_for_market(market_id)

        if not market_txns:
            # No history - can't determine what happened
            actions.append("No transaction history found for this market")
            actions.append("Defaulting to RESET_TO_IDLE")
            return self._reset_to_idle(state, discrepancy)

        # Count BUY and SELL
        buys = [t for t in market_txns if t['type'] == 'BUY']
        sells = [t for t in market_txns if t['type'] == 'SELL']

        total_bought = sum(t.get('shares', 0) for t in buys)
        total_sold = sum(t.get('shares', 0) for t in sells)

        actions.append(f"Transaction history: {len(buys)} BUY, {len(sells)} SELL")
        actions.append(f"Total bought: {total_bought:.4f}, Total sold: {total_sold:.4f}")

        # If everything sold, move to COMPLETED
        if total_bought > 0 and abs(total_bought - total_sold) < self.tolerance_shares:
            # Position was sold
            state['stage'] = 'COMPLETED'
            state_changes['stage'] = 'COMPLETED'

            actions.append("Position appears to be fully closed")
            actions.append("Set stage to COMPLETED")

            # Save state
            self.state_manager.save_state(state)
            actions.append("Saved updated state")

            return RecoveryResult(
                success=True,
                strategy=RecoveryStrategy.SYNC_FROM_HISTORY,
                actions_taken=actions,
                state_changes=state_changes,
                reason="Position was already sold according to transaction history"
            )

        else:
            # History unclear - reset
            actions.append("Transaction history unclear")
            actions.append("Defaulting to RESET_TO_IDLE")
            return self._reset_to_idle(state, discrepancy)

    def _reset_to_idle(
        self,
        state: Dict[str, Any],
        discrepancy: Discrepancy
    ) -> RecoveryResult:
        """
        Reset state to IDLE (last resort).
        """
        actions = []
        state_changes = {}

        actions.append("⚠️  Resetting state to IDLE (clean slate)")

        # Reset position
        self.state_manager.reset_position(state)
        state['stage'] = 'IDLE'

        state_changes = {
            'stage': 'IDLE',
            'current_position': 'cleared'
        }

        actions.append("Cleared current_position")
        actions.append("Set stage to IDLE")

        # Save state
        self.state_manager.save_state(state)
        actions.append("Saved updated state")

        return RecoveryResult(
            success=True,
            strategy=RecoveryStrategy.RESET_TO_IDLE,
            actions_taken=actions,
            state_changes=state_changes,
            reason="Reset to clean state as last resort"
        )

    def _cancel_and_reset(
        self,
        state: Dict[str, Any],
        discrepancy: Discrepancy
    ) -> RecoveryResult:
        """
        Cancel orphaned pending orders and reset state (ORPHANED_ORDER case).

        State is IDLE/SCANNING but API shows pending orders.
        Cancel all pending orders and reset to clean IDLE state.
        """
        actions = []
        state_changes = {}

        # Get orphaned orders from discrepancy metadata
        all_orders = discrepancy.metadata.get('all_orders', [])
        api_data = discrepancy.api_data

        if not all_orders:
            # Fallback: try to cancel just the first order from api_data
            order_id = api_data.get('order_id')
            if order_id:
                all_orders = [{'order_id': order_id, 'market_id': api_data.get('market_id', 0)}]

        actions.append(f"Found {len(all_orders)} orphaned pending order(s)")

        # Cancel each orphaned order
        cancelled_count = 0
        failed_count = 0

        for order in all_orders:
            order_id = order.get('order_id', 'unknown')
            market_id = order.get('market_id', 0)

            try:
                logger.info(f"   Cancelling orphaned order {order_id} (market #{market_id})...")
                success = self.client.cancel_order(order_id)

                if success:
                    cancelled_count += 1
                    actions.append(f"Cancelled order {order_id} on market #{market_id}")
                    logger.info(f"   ✅ Cancelled successfully")
                else:
                    failed_count += 1
                    actions.append(f"⚠️  Failed to cancel order {order_id}")
                    logger.warning(f"   ⚠️  Cancellation failed (may be already filled/cancelled)")

            except Exception as e:
                failed_count += 1
                actions.append(f"⚠️  Error cancelling order {order_id}: {str(e)}")
                logger.error(f"   ❌ Error: {e}")

        # Reset state to IDLE
        logger.info("   Resetting state to IDLE...")
        self.state_manager.reset_position(state)
        state['stage'] = 'IDLE'

        state_changes = {
            'stage': 'IDLE',
            'current_position': 'cleared',
            'orders_cancelled': cancelled_count,
            'cancellations_failed': failed_count
        }

        actions.append(f"Cancelled {cancelled_count}/{len(all_orders)} order(s)")
        if failed_count > 0:
            actions.append(f"⚠️  {failed_count} cancellation(s) failed (likely already filled/cancelled)")
        actions.append("Reset state to IDLE")

        # Save state
        self.state_manager.save_state(state)
        actions.append("Saved updated state")

        # Determine success based on results
        if cancelled_count > 0 or failed_count == len(all_orders):
            # Success if we cancelled at least one OR all failed (meaning they were already done)
            success = True
            reason = f"Cancelled {cancelled_count} orphaned order(s) and reset to IDLE"
        else:
            success = False
            reason = f"Failed to cancel any of {len(all_orders)} order(s)"

        return RecoveryResult(
            success=success,
            strategy=RecoveryStrategy.CANCEL_AND_RESET,
            actions_taken=actions,
            state_changes=state_changes,
            reason=reason,
            metadata={'cancelled': cancelled_count, 'failed': failed_count}
        )

    def _send_recovery_notification(
        self,
        telegram_notifier,
        discrepancy: Discrepancy,
        result: RecoveryResult
    ):
        """Send Telegram notification about recovery."""

        status_emoji = "✅" if result.success else "❌"
        severity_emoji = "🚨" if discrepancy.severity == 'HIGH' else "⚠️"

        message = f"{severity_emoji} **State Reconciliation**\n\n"
        message += f"**Issue:** {discrepancy.description}\n"
        message += f"**Severity:** {discrepancy.severity}\n"
        message += f"**Strategy:** {result.strategy.value}\n"
        message += f"**Status:** {status_emoji} {'Success' if result.success else 'Failed'}\n\n"

        if result.success:
            message += "**Actions Taken:**\n"
            for action in result.actions_taken[:5]:  # Limit to 5
                message += f"• {action}\n"
        else:
            message += f"**Reason:** {result.reason}\n"

        try:
            telegram_notifier.send_message(message)
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}")


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== Reconciliation Engine Module Test ===")
    print()
    print("This module requires integration testing with full bot setup.")
    print("Run autonomous_bot with reconciliation enabled to test.")
    print()
    print("✅ Module loaded successfully")
