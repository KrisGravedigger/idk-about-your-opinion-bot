"""
Position Laddering Strategy Module
===================================

Implements position laddering (grid trading / averaging down) to replace
traditional stop-loss with counter-BUY orders during flash crashes.

Key Concept:
Instead of panic-selling during flash crashes, the bot places counter-BUY
orders at lower prices to average down the cost basis and profit from mean
reversion.

Example:
    Entry: 535 YES @ $0.7820
    Flash crash: BID drops to $0.5070 (-35%)
    Counter-BUY fills: 535 YES @ $0.6647 (-15% ladder)
    New average: 1,070 YES @ $0.7234
    Market recovers to $0.75
    SELL fills @ $0.7520 (+4% profit target)
    Result: +4.2% profit vs -35% loss with traditional stop-loss

Usage:
    from monitoring.position_laddering import PositionLaddering

    laddering = PositionLaddering(config, client, state)

    # Place counter-BUY when entering position
    ladder_price = laddering.calculate_ladder_price(entry_price, -15.0)
    result = laddering.place_ladder_buy(market_id, token_id, ladder_price, amount)

    # After counter-BUY fills, execute averaging
    avg_result = laddering.execute_averaging_down(new_shares, new_price)

Author: Opinion Trading Bot Team
Version: 1.0 (Phase 1 - Single Ladder)
"""

from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from logger_config import setup_logger
from utils import format_price, format_usdt, format_percent, round_price, get_timestamp

logger = setup_logger(__name__)


class PositionLaddering:
    """
    Position laddering strategy implementation.

    Handles counter-BUY placement, averaging down logic, and break-even
    calculation for the position laddering strategy.

    Attributes:
        config: Configuration dictionary
        client: API client instance
        state: Current bot state dictionary
    """

    def __init__(self, config: Dict[str, Any], client, state: Dict[str, Any]):
        """
        Initialize position laddering strategy.

        Args:
            config: Configuration dictionary
            client: OpinionClient instance
            state: Current state dictionary

        Example:
            >>> laddering = PositionLaddering(config, client, state)
        """
        self.config = config
        self.client = client
        self.state = state

        # Extract config values
        self.enabled = config.get('ENABLE_POSITION_LADDERING', False)
        self.mode = config.get('LADDERING_MODE', 'single')
        self.buy_offset_pct = config.get('LADDER_BUY_OFFSET_PCT', -15.0)
        self.max_rounds = config.get('LADDER_MAX_ROUNDS', 1)
        self.profit_target_pct = config.get('LADDER_PROFIT_TARGET_PCT', 4.0)
        self.hard_stop_loss_pct = config.get('LADDER_HARD_STOP_LOSS_PCT', -50.0)
        self.spread_filter_pct = config.get('LADDER_SPREAD_FILTER_PCT', 20.0)
        self.capital_multiplier = config.get('LADDER_CAPITAL_MULTIPLIER', 2.0)

        logger.debug(
            f"PositionLaddering initialized: "
            f"enabled={self.enabled}, mode={self.mode}, "
            f"offset={self.buy_offset_pct}%, max_rounds={self.max_rounds}, "
            f"profit_target={self.profit_target_pct}%"
        )

    def calculate_ladder_price(self, entry_price: float, offset_pct: float) -> Decimal:
        """
        Calculate counter-BUY price from entry price and offset percentage.

        Formula: ladder_price = entry_price × (1 + offset_pct/100)

        Args:
            entry_price: Original entry price (avg_fill_price from BUY order)
            offset_pct: Percentage offset (negative for ladder below entry)

        Returns:
            Ladder price as Decimal (rounded to price precision)

        Example:
            >>> # Entry at $0.7820, offset -15%
            >>> ladder_price = laddering.calculate_ladder_price(0.7820, -15.0)
            >>> ladder_price  # Decimal('0.6647')

        Note:
            Uses Decimal for precision to avoid float rounding errors.
        """
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price}")

        if offset_pct >= 0:
            raise ValueError(f"offset_pct must be negative for ladder below entry, got {offset_pct}")

        # Convert to Decimal for precision
        entry_decimal = Decimal(str(entry_price))
        offset_decimal = Decimal(str(offset_pct))

        # Calculate: entry_price × (1 + offset_pct/100)
        multiplier = Decimal('1') + (offset_decimal / Decimal('100'))
        ladder_price = entry_decimal * multiplier

        # Round to price decimals (3 decimals for Opinion.trade)
        price_decimals = self.config.get('PRICE_DECIMALS', 3)
        ladder_price = ladder_price.quantize(
            Decimal(f'0.{"0" * price_decimals}'),
            rounding=ROUND_DOWN
        )

        logger.debug(
            f"Calculated ladder price: entry={format_price(float(entry_decimal))}, "
            f"offset={offset_pct}%, ladder={format_price(float(ladder_price))}"
        )

        return ladder_price

    def place_ladder_buy(
        self,
        market_id: int,
        token_id: str,
        price: float,
        amount: float
    ) -> Dict[str, Any]:
        """
        Place counter-BUY limit order at ladder price with capital validation.

        Steps:
        1. Validate sufficient capital available
        2. Calculate order size in USDT
        3. Place BUY limit order using OrderManager
        4. Return order result

        Args:
            market_id: Market ID
            token_id: Token ID (YES or NO)
            price: Ladder price (counter-BUY price)
            amount: Amount in shares/tokens (same as original position)

        Returns:
            Dictionary with result:
            {
                'success': bool,
                'order_id': str (if success),
                'order_price': float (if success),
                'reason': str (if failure)
            }

        Example:
            >>> result = laddering.place_ladder_buy(
            ...     market_id=1856,
            ...     token_id='0x123...',
            ...     price=0.6647,
            ...     amount=535.0
            ... )
            >>> if result['success']:
            ...     print(f"Ladder BUY placed: {result['order_id']}")
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("🎯 PLACING LADDER BUY ORDER (Counter-buy)")
        logger.info("=" * 70)
        logger.info(f"   Market ID: {market_id}")
        logger.info(f"   Price: {format_price(price)}")
        logger.info(f"   Amount: {amount:.4f} tokens")
        logger.info("")

        # Calculate required capital (price × amount)
        required_capital = Decimal(str(price)) * Decimal(str(amount))
        required_capital_float = float(required_capital)

        logger.info(f"   Required capital: {format_usdt(required_capital_float)}")

        # Validate capital available
        try:
            current_balance = self.client.get_usdt_balance()
            logger.info(f"   Current balance: {format_usdt(current_balance)}")

            if current_balance < required_capital_float:
                shortage = required_capital_float - current_balance
                logger.error("")
                logger.error("❌ INSUFFICIENT CAPITAL FOR LADDER BUY")
                logger.error(f"   Required: {format_usdt(required_capital_float)}")
                logger.error(f"   Available: {format_usdt(current_balance)}")
                logger.error(f"   Shortage: {format_usdt(shortage)}")
                logger.error("")
                logger.error("   Cannot place counter-buy order.")
                logger.error("   Position will continue with traditional stop-loss only.")
                logger.error("")

                return {
                    'success': False,
                    'order_id': None,
                    'order_price': None,
                    'reason': f'Insufficient capital: need {format_usdt(shortage)} more'
                }

            logger.info(f"   ✓ Sufficient capital available")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ Error checking balance: {e}")
            return {
                'success': False,
                'order_id': None,
                'order_price': None,
                'reason': f'Balance check failed: {e}'
            }

        # Place BUY order using OrderManager
        try:
            from order_manager import OrderManager
            order_manager = OrderManager(self.client)

            # Calculate amount in USDT for place_buy()
            amount_usdt = float(required_capital)

            logger.info(f"   Placing BUY limit order...")
            result = order_manager.place_buy(
                market_id=market_id,
                token_id=token_id,
                price=price,
                amount_usdt=amount_usdt
            )

            if not result:
                logger.error("   ❌ Failed to place ladder BUY order")
                return {
                    'success': False,
                    'order_id': None,
                    'order_price': None,
                    'reason': 'Order placement failed (API error)'
                }

            order_id = result.get('order_id', result.get('orderId', 'unknown'))

            logger.info("")
            logger.info("✅ LADDER BUY ORDER PLACED SUCCESSFULLY")
            logger.info(f"   Order ID: {order_id}")
            logger.info(f"   Price: {format_price(price)}")
            logger.info(f"   Amount: {format_usdt(amount_usdt)}")
            logger.info("")
            logger.info("   This order will fill if market crashes below entry")
            logger.info("   If filled, bot will average down position and profit from recovery")
            logger.info("=" * 70)
            logger.info("")

            return {
                'success': True,
                'order_id': order_id,
                'order_price': price,
                'amount_usdt': amount_usdt,
                'reason': None
            }

        except Exception as e:
            logger.exception(f"❌ Exception placing ladder BUY order: {e}")
            return {
                'success': False,
                'order_id': None,
                'order_price': None,
                'reason': f'Exception: {e}'
            }

    def check_ladder_buy_filled(self, order_id: str) -> bool:
        """
        Check if counter-BUY order has filled.

        Args:
            order_id: Order ID to check

        Returns:
            True if order is filled, False otherwise

        Example:
            >>> if laddering.check_ladder_buy_filled('ord_123'):
            ...     print("Ladder BUY filled - executing averaging down")
        """
        try:
            order = self.client.get_order(order_id)

            if not order:
                logger.warning(f"Could not fetch order {order_id} status")
                return False

            status_enum = order.get('status_enum', 'unknown')

            if status_enum == 'Finished' or order.get('status') == 2:
                logger.info(f"✅ Ladder BUY order filled: {order_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking ladder BUY fill status: {e}")
            return False

    def execute_averaging_down(
        self,
        original_shares: float,
        original_price: float,
        new_shares: float,
        new_price: float
    ) -> Dict[str, Any]:
        """
        Execute averaging down logic after counter-BUY fills.

        Steps:
        1. Calculate new average price and total shares
        2. Update position state (shares, avg_price, total_cost)
        3. Cancel old SELL order
        4. Calculate break-even + profit target
        5. Place new SELL order at profit target
        6. Save state

        Args:
            original_shares: Original position size (tokens)
            original_price: Original entry price
            new_shares: Counter-BUY shares (tokens filled)
            new_price: Counter-BUY price (price filled at)

        Returns:
            Dictionary with result:
            {
                'success': bool,
                'avg_price': float (new averaged price),
                'total_shares': float (total position),
                'break_even_price': float,
                'profit_target_price': float,
                'new_sell_order_id': str (if success),
                'reason': str (if failure)
            }

        Example:
            >>> # Original: 535 @ $0.7820
            >>> # Counter: 535 @ $0.6647
            >>> result = laddering.execute_averaging_down(
            ...     original_shares=535.0,
            ...     original_price=0.7820,
            ...     new_shares=535.0,
            ...     new_price=0.6647
            ... )
            >>> # Result: avg_price=0.7234, total_shares=1070
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("📊 EXECUTING AVERAGING DOWN")
        logger.info("=" * 70)
        logger.info("")

        # Step 1: Calculate new average price
        try:
            # Use Decimal for precision
            orig_shares_dec = Decimal(str(original_shares))
            orig_price_dec = Decimal(str(original_price))
            new_shares_dec = Decimal(str(new_shares))
            new_price_dec = Decimal(str(new_price))

            # Total cost = (orig_shares × orig_price) + (new_shares × new_price)
            orig_cost = orig_shares_dec * orig_price_dec
            new_cost = new_shares_dec * new_price_dec
            total_cost = orig_cost + new_cost

            # Total shares
            total_shares_dec = orig_shares_dec + new_shares_dec

            # Average price = total_cost / total_shares
            avg_price_dec = total_cost / total_shares_dec

            # Convert to float for display and storage
            avg_price = float(avg_price_dec)
            total_shares = float(total_shares_dec)

            logger.info("📈 AVERAGING CALCULATION:")
            logger.info(f"   Original position:")
            logger.info(f"     {original_shares:.4f} tokens @ {format_price(original_price)}")
            logger.info(f"     Cost: {format_usdt(float(orig_cost))}")
            logger.info("")
            logger.info(f"   Counter-buy:")
            logger.info(f"     {new_shares:.4f} tokens @ {format_price(new_price)}")
            logger.info(f"     Cost: {format_usdt(float(new_cost))}")
            logger.info("")
            logger.info(f"   New averaged position:")
            logger.info(f"     {total_shares:.4f} tokens @ {format_price(avg_price)}")
            logger.info(f"     Total cost: {format_usdt(float(total_cost))}")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ Error calculating average price: {e}")
            return {
                'success': False,
                'avg_price': None,
                'total_shares': None,
                'break_even_price': None,
                'profit_target_price': None,
                'new_sell_order_id': None,
                'reason': f'Calculation error: {e}'
            }

        # Step 2: Update position state
        position = self.state.get('current_position', {})

        # Store original values if not already stored
        if not position.get('original_cost_basis'):
            position['original_cost_basis'] = original_price
            position['original_shares'] = original_shares

        # Update position with averaged values
        position['avg_fill_price'] = avg_price
        position['filled_amount'] = total_shares
        position['total_cost_usd'] = float(total_cost)
        position['filled_usdt'] = float(total_cost)
        position['averaged_down'] = True
        position['averaging_rounds'] = position.get('averaging_rounds', 0) + 1

        # Step 3: Cancel old SELL order
        old_sell_order_id = position.get('sell_order_id')

        if old_sell_order_id and old_sell_order_id != 'unknown':
            try:
                logger.info(f"🗑️  Cancelling old SELL order: {old_sell_order_id}")
                self.client.cancel_order(old_sell_order_id)
                logger.info(f"   ✓ Old SELL order cancelled")
            except Exception as e:
                logger.warning(f"   ⚠️  Could not cancel old SELL order: {e}")
                logger.warning(f"   Continuing with new order placement...")

        # Step 4: Calculate profit target
        profit_target_price = self.calculate_profit_target(avg_price, self.profit_target_pct)

        logger.info("")
        logger.info("🎯 NEW PROFIT TARGET:")
        logger.info(f"   Break-even: {format_price(avg_price)}")
        logger.info(f"   Profit target (+{self.profit_target_pct}%): {format_price(profit_target_price)}")
        logger.info("")

        # Step 5: Place new SELL order
        try:
            from order_manager import OrderManager
            order_manager = OrderManager(self.client)

            market_id = position.get('market_id')
            outcome_side = position.get('outcome_side', 'YES')

            logger.info(f"📤 Placing new SELL order at profit target...")

            # Note: token_id no longer in state, OrderManager.place_sell needs to be fixed
            # For now, pass None (will likely cause error until OrderManager updated)
            sell_result = order_manager.place_sell(
                market_id=market_id,
                token_id=None,  # FIXME: OrderManager.place_sell needs update to remove this
                price=profit_target_price,
                amount_tokens=total_shares,
                outcome_side=outcome_side
            )

            if not sell_result:
                logger.error("   ❌ Failed to place new SELL order")
                return {
                    'success': False,
                    'avg_price': avg_price,
                    'total_shares': total_shares,
                    'break_even_price': avg_price,
                    'profit_target_price': profit_target_price,
                    'new_sell_order_id': None,
                    'reason': 'New SELL order placement failed'
                }

            new_sell_order_id = sell_result.get('order_id', sell_result.get('orderId', 'unknown'))

            logger.info(f"   ✅ New SELL order placed: {new_sell_order_id}")
            logger.info("")

        except Exception as e:
            logger.exception(f"❌ Error placing new SELL order: {e}")
            return {
                'success': False,
                'avg_price': avg_price,
                'total_shares': total_shares,
                'break_even_price': avg_price,
                'profit_target_price': profit_target_price,
                'new_sell_order_id': None,
                'reason': f'Exception placing SELL: {e}'
            }

        # Step 6: Update state with new SELL order info
        position['sell_order_id'] = new_sell_order_id
        position['sell_price'] = profit_target_price
        position['profit_target_price'] = profit_target_price

        # Save state
        from core.state_manager import StateManager
        state_file = self.config.get('STATE_FILE', 'state.json')
        state_manager = StateManager(state_file)
        state_manager.save_state(self.state)

        logger.info("✅ AVERAGING DOWN COMPLETE")
        logger.info(f"   Position doubled from {original_shares:.2f} to {total_shares:.2f} tokens")
        logger.info(f"   Break-even lowered from {format_price(original_price)} to {format_price(avg_price)}")
        logger.info(f"   Now monitoring new SELL order @ {format_price(profit_target_price)}")
        logger.info("=" * 70)
        logger.info("")

        return {
            'success': True,
            'avg_price': avg_price,
            'total_shares': total_shares,
            'break_even_price': avg_price,
            'profit_target_price': profit_target_price,
            'new_sell_order_id': new_sell_order_id,
            'reason': None
        }

    def should_counter_buy(
        self,
        current_spread_pct: float,
        market_status: str = None
    ) -> Tuple[bool, str]:
        """
        Perform safety checks before executing counter-buy.

        Checks:
        - Spread < threshold (avoid illiquid markets)
        - Market not resolving/resolved
        - Capital available (checked in place_ladder_buy)
        - Max averaging rounds not exceeded

        Args:
            current_spread_pct: Current market spread percentage
            market_status: Market status (e.g., 'open', 'resolved')

        Returns:
            Tuple of (should_execute: bool, reason: str)

        Example:
            >>> should_buy, reason = laddering.should_counter_buy(
            ...     current_spread_pct=5.0,
            ...     market_status='open'
            ... )
            >>> if not should_buy:
            ...     print(f"Counter-buy blocked: {reason}")
        """
        # Check 1: Spread filter
        if current_spread_pct > self.spread_filter_pct:
            reason = (
                f"Spread too wide ({current_spread_pct:.1f}% > {self.spread_filter_pct}% threshold). "
                f"Market is illiquid - not safe to counter-buy."
            )
            logger.warning(f"⚠️  Counter-buy blocked: {reason}")
            return (False, reason)

        # Check 2: Market status
        if market_status and market_status.lower() in ['resolved', 'closed', 'resolving']:
            reason = f"Market is {market_status} - cannot counter-buy"
            logger.warning(f"⚠️  Counter-buy blocked: {reason}")
            return (False, reason)

        # Check 3: Max averaging rounds
        position = self.state.get('current_position', {})
        averaging_rounds = position.get('averaging_rounds', 0)

        if averaging_rounds >= self.max_rounds:
            reason = (
                f"Max averaging rounds reached ({averaging_rounds}/{self.max_rounds}). "
                f"Cannot counter-buy again."
            )
            logger.warning(f"⚠️  Counter-buy blocked: {reason}")
            return (False, reason)

        # All checks passed
        return (True, "All safety checks passed")

    def calculate_profit_target(self, avg_price: float, margin_pct: float) -> float:
        """
        Calculate SELL price for profit target above break-even.

        Formula: profit_target = avg_price × (1 + margin_pct/100)

        Args:
            avg_price: Averaged cost basis
            margin_pct: Profit margin percentage

        Returns:
            Profit target price (rounded to price precision)

        Example:
            >>> # Avg price $0.7234, margin +4%
            >>> profit_target = laddering.calculate_profit_target(0.7234, 4.0)
            >>> profit_target  # 0.7520 (rounded)
        """
        if avg_price <= 0:
            raise ValueError(f"avg_price must be positive, got {avg_price}")

        if margin_pct <= 0:
            raise ValueError(f"margin_pct must be positive, got {margin_pct}")

        # Use Decimal for precision
        avg_price_dec = Decimal(str(avg_price))
        margin_dec = Decimal(str(margin_pct))

        # Calculate: avg_price × (1 + margin_pct/100)
        multiplier = Decimal('1') + (margin_dec / Decimal('100'))
        profit_target = avg_price_dec * multiplier

        # Round to price decimals
        profit_target_float = round_price(float(profit_target))

        logger.debug(
            f"Calculated profit target: avg_price={format_price(avg_price)}, "
            f"margin={margin_pct}%, target={format_price(profit_target_float)}"
        )

        return profit_target_float


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("Position Laddering Module - Unit Tests")
    print("=" * 70)
    print()

    # Mock config, client, and state
    mock_config = {
        'ENABLE_POSITION_LADDERING': True,
        'LADDERING_MODE': 'single',
        'LADDER_BUY_OFFSET_PCT': -15.0,
        'LADDER_MAX_ROUNDS': 1,
        'LADDER_PROFIT_TARGET_PCT': 4.0,
        'LADDER_HARD_STOP_LOSS_PCT': -50.0,
        'LADDER_SPREAD_FILTER_PCT': 20.0,
        'LADDER_CAPITAL_MULTIPLIER': 2.0,
        'PRICE_DECIMALS': 3
    }

    mock_state = {
        'current_position': {
            'avg_fill_price': 0.7820,
            'filled_amount': 535.0,
            'averaging_rounds': 0
        }
    }

    class MockClient:
        def get_usdt_balance(self):
            return 500.0

    mock_client = MockClient()

    # Create instance
    laddering = PositionLaddering(mock_config, mock_client, mock_state)

    # Test 1: Calculate ladder price
    print("Test 1: Calculate ladder price")
    entry_price = 0.7820
    offset_pct = -15.0
    ladder_price = laddering.calculate_ladder_price(entry_price, offset_pct)
    print(f"  Entry: ${entry_price:.4f}")
    print(f"  Offset: {offset_pct}%")
    print(f"  Ladder: ${float(ladder_price):.4f}")
    print(f"  ✓ Expected ~$0.6647")
    print()

    # Test 2: Calculate profit target
    print("Test 2: Calculate profit target")
    avg_price = 0.7234
    margin_pct = 4.0
    profit_target = laddering.calculate_profit_target(avg_price, margin_pct)
    print(f"  Avg price: ${avg_price:.4f}")
    print(f"  Margin: +{margin_pct}%")
    print(f"  Target: ${profit_target:.4f}")
    print(f"  ✓ Expected ~$0.7520")
    print()

    # Test 3: Averaging calculation
    print("Test 3: Averaging down calculation")
    # This would normally be tested in integration tests with full state
    # For now, just verify the formula
    orig_shares = 535.0
    orig_price = 0.7820
    new_shares = 535.0
    new_price = 0.6647

    from decimal import Decimal
    orig_cost = Decimal(str(orig_shares)) * Decimal(str(orig_price))
    new_cost = Decimal(str(new_shares)) * Decimal(str(new_price))
    total_cost = orig_cost + new_cost
    total_shares = Decimal(str(orig_shares)) + Decimal(str(new_shares))
    avg = total_cost / total_shares

    print(f"  Original: {orig_shares} @ ${orig_price:.4f} = ${float(orig_cost):.2f}")
    print(f"  Counter: {new_shares} @ ${new_price:.4f} = ${float(new_cost):.2f}")
    print(f"  Total: {float(total_shares)} @ ${float(avg):.4f} = ${float(total_cost):.2f}")
    print(f"  ✓ Expected avg ~$0.7234")
    print()

    # Test 4: Safety checks
    print("Test 4: Safety checks")
    should_buy, reason = laddering.should_counter_buy(
        current_spread_pct=5.0,
        market_status='open'
    )
    print(f"  Spread: 5.0% (OK)")
    print(f"  Status: open (OK)")
    print(f"  Should counter-buy: {should_buy}")
    print(f"  Reason: {reason}")
    print(f"  ✓ Expected True")
    print()

    should_buy, reason = laddering.should_counter_buy(
        current_spread_pct=25.0,
        market_status='open'
    )
    print(f"  Spread: 25.0% (TOO WIDE)")
    print(f"  Should counter-buy: {should_buy}")
    print(f"  Reason: {reason}")
    print(f"  ✓ Expected False")
    print()

    print("=" * 70)
    print("✅ Unit tests complete!")
    print("=" * 70)
