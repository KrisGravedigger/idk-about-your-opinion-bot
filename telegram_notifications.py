"""
Telegram Notifications Service
================================

Sends notifications to Telegram for important bot events:
- Bot start/stop with statistics
- State changes (buy pending, sell pending)
- Stop-loss triggers
- Periodic heartbeat updates

Requires:
    pip install requests

Configuration in .env:
    TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
    TELEGRAM_CHAT_ID=your_chat_id

Usage:
    from telegram_notifications import TelegramNotifier

    notifier = TelegramNotifier()
    notifier.send_bot_start(stats, config)
    notifier.send_heartbeat(state, orderbook, balance)
"""

import os
import requests
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from logger_config import setup_logger

logger = setup_logger(__name__)


class TelegramNotifier:
    """
    Telegram notification service for bot events.

    Attributes:
        bot_token: Telegram bot token from BotFather
        chat_id: Telegram chat ID to send messages to
        enabled: Whether notifications are enabled
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token (defaults to TELEGRAM_BOT_TOKEN env var)
            chat_id: Telegram chat ID (defaults to TELEGRAM_CHAT_ID env var)
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)

        if self.enabled:
            logger.info("📱 Telegram notifications enabled")
            logger.debug(f"   Chat ID: {self.chat_id}")
        else:
            logger.info("📱 Telegram notifications disabled (no credentials)")

        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
        async_send: bool = True
    ) -> bool:
        """
        Send a message to Telegram.

        Args:
            message: Message text (supports HTML formatting)
            parse_mode: Message parse mode (HTML or Markdown)
            disable_notification: Send silently without notification
            async_send: If True, send in background thread (non-blocking)

        Returns:
            True if sent successfully, False otherwise
            Note: For async sends, returns True immediately (doesn't wait for response)
        """
        if not self.enabled:
            logger.debug("Telegram disabled, skipping message")
            return False

        # If async requested, send in background thread
        if async_send:
            import threading
            thread = threading.Thread(
                target=self._send_message_sync,
                args=(message, parse_mode, disable_notification),
                daemon=True
            )
            thread.start()
            return True  # Return immediately, don't wait for thread

        # Synchronous send (blocking)
        return self._send_message_sync(message, parse_mode, disable_notification)

    def _send_message_sync(
        self,
        message: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False
    ) -> bool:
        """
        Internal method: Send message synchronously (blocking).

        Args:
            message: Message text
            parse_mode: Parse mode (HTML/Markdown)
            disable_notification: Silent notification

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_notification": disable_notification
            }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            logger.debug("✅ Telegram message sent")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def send_bot_start(
        self,
        stats: Dict[str, Any],
        config: Dict[str, Any],
        balance: float
    ) -> bool:
        """
        Send bot startup notification with current statistics.

        Args:
            stats: P&L statistics dictionary
            config: Bot configuration dictionary
            balance: Current USDT balance

        Returns:
            True if sent successfully
        """
        capital_mode = config.get('CAPITAL_MODE', 'unknown')
        capital_info = ""

        if capital_mode == 'fixed':
            capital_info = f"${config.get('CAPITAL_AMOUNT_USDT', 0):.2f}"
        elif capital_mode == 'percentage':
            capital_info = f"{config.get('CAPITAL_PERCENTAGE', 0):.0f}%"

        scoring_profile = config.get('SCORING_PROFILE', 'default')

        pnl_sign = "+" if stats.get('total_pnl_usdt', 0) >= 0 else ""
        pnl_emoji = "💰" if stats.get('total_pnl_usdt', 0) >= 0 else "📉"

        message = f"""
🚀 <b>BOT STARTED</b>

📊 <b>Current Statistics:</b>
   • Total trades: {stats.get('total_trades', 0)}
   • Win rate: {stats.get('win_rate_percent', 0):.1f}%
   • {pnl_emoji} Total P&L: {pnl_sign}${stats.get('total_pnl_usdt', 0):.2f}
   • Avg P&L/trade: {pnl_sign}${stats.get('total_pnl_percent', 0):.2f}

💼 <b>Configuration:</b>
   • Available capital: ${balance:.2f}
   • Capital mode: {capital_mode} ({capital_info})
   • Scoring profile: {scoring_profile}
   • Stop-loss: {'ENABLED' if config.get('ENABLE_STOP_LOSS') else 'DISABLED'}

⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message.strip())

    def send_bot_stop(
        self,
        stats: Dict[str, Any],
        last_logs: List[str]
    ) -> bool:
        """
        Send bot stop notification with last log lines and final statistics.

        Args:
            stats: P&L statistics dictionary
            last_logs: Last 20 lines of log before shutdown

        Returns:
            True if sent successfully
        """
        pnl_sign = "+" if stats.get('total_pnl_usdt', 0) >= 0 else ""
        pnl_emoji = "💰" if stats.get('total_pnl_usdt', 0) >= 0 else "📉"

        # Format log lines (escape HTML and limit length)
        log_text = "\n".join(last_logs[-20:]) if last_logs else "No recent logs"
        if len(log_text) > 500:
            log_text = "..." + log_text[-500:]

        log_text = log_text.replace('<', '&lt;').replace('>', '&gt;')

        message = f"""
⛔ <b>BOT STOPPED</b>

📊 <b>Final Statistics:</b>
   • Total trades: {stats.get('total_trades', 0)}
   • Win rate: {stats.get('win_rate_percent', 0):.1f}%
   • {pnl_emoji} Total P&L: {pnl_sign}${stats.get('total_pnl_usdt', 0):.2f}
   • Avg P&L/trade: {pnl_sign}${stats.get('total_pnl_percent', 0):.2f}

📝 <b>Last log lines:</b>
<pre>{log_text}</pre>

⏰ Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        # Send synchronously (async_send=False) to ensure message is sent before program exits
        return self.send_message(message.strip(), async_send=False)

    def send_heartbeat(
        self,
        stage: str,
        market_info: Optional[Dict[str, Any]] = None,
        order_info: Optional[Dict[str, Any]] = None,
        balance: float = 0,
        position_value: float = 0,
        outcome_side: Optional[str] = None
    ) -> bool:
        """
        Send periodic heartbeat update.

        Args:
            stage: Current bot stage
            market_info: Current market information (spread, orderbook, etc.)
            order_info: Current order details (price, amounts, position in book)
            balance: Available USDT balance
            position_value: Current position value in USDT
            outcome_side: Market outcome side (YES/NO) if in position

        Returns:
            True if sent successfully
        """
        status_emoji = {
            'IDLE': '💤',
            'SCANNING': '🔍',
            'BUY_PLACED': '📝',
            'BUY_MONITORING': '👀',
            'BUY_FILLED': '✅',
            'SELL_PLACED': '📝',
            'SELL_MONITORING': '👀',
            'COMPLETED': '✅'
        }.get(stage, '❓')

        message = f"""
💓 <b>HEARTBEAT</b>

📍 <b>Status:</b> {status_emoji} {stage}
"""

        # Add outcome side (YES/NO) if in position
        if outcome_side:
            side_emoji = '✅' if outcome_side == 'YES' else '❌'
            message += f"📌 <b>Market side:</b> {side_emoji} {outcome_side}\n"

        message += f"""
💰 <b>Balance:</b>
   • Available: ${balance:.2f}
   • Position value: ${position_value:.2f}
"""

        if market_info:
            market_id = market_info.get('market_id', 'N/A')
            market_title = market_info.get('market_title', 'N/A')
            spread = market_info.get('spread', 0)
            best_bid = market_info.get('best_bid', 0)
            best_ask = market_info.get('best_ask', 0)

            # Truncate title if too long
            if len(market_title) > 60:
                market_title = market_title[:57] + "..."

            message += f"""
📊 <b>Market:</b> #{market_id}
   {market_title}
   • Spread: ${spread:.4f}
   • Best bid: ${best_bid:.4f}
   • Best ask: ${best_ask:.4f}
"""

        # Add order details if available
        if order_info:
            order_side = order_info.get('side', 'BUY')
            our_price = order_info.get('our_price', 0)
            order_amount = order_info.get('order_amount', 0)
            filled_amount = order_info.get('filled_amount', 0)
            filled_percent = order_info.get('filled_percent', 0)
            distance_from_best = order_info.get('distance_from_best', 0)
            distance_percent = order_info.get('distance_percent', 0)
            position_in_book = order_info.get('position_in_book', {})

            # Emoji for order side
            side_emoji = '🟢' if order_side == 'BUY' else '🔴'

            message += f"""
{side_emoji} <b>{order_side} Order:</b>
   • Price: ${our_price:.4f}
   • Amount: ${order_amount:.2f}
   • Filled: ${filled_amount:.2f} ({filled_percent:.1f}%)
"""

            # Add orderbook position info
            pos = position_in_book.get('position', 0)
            total = position_in_book.get('total_levels', 0)
            ahead_volume = position_in_book.get('ahead_volume', 0)

            if pos > 0:
                # Show distance from best price
                direction = "below" if order_side == 'BUY' else "above"
                message += f"""
📈 <b>Orderbook Position:</b>
   • {pos} level(s) {direction} best price
   • Distance: ${abs(distance_from_best):.4f} ({abs(distance_percent):.2f}%)
   • Volume ahead: {ahead_volume:.0f} shares
"""

                # Add simple visualization of levels ahead
                levels_ahead = position_in_book.get('levels_ahead', [])
                if levels_ahead:
                    message += "\n   <b>Levels ahead:</b>\n"
                    for level in levels_ahead[:3]:  # Show top 3 levels
                        lvl_price = level['price']
                        lvl_size = level['size']
                        # Create simple bar visualization
                        bar_length = min(int(lvl_size / 100), 20)  # Scale: 100 shares = 1 char, max 20
                        bar = '█' * bar_length if bar_length > 0 else '▏'
                        message += f"   ${lvl_price:.4f} {bar} {lvl_size:.0f}\n"
            else:
                # Our order is at the best price!
                message += f"\n✨ <b>At best {order_side.lower()} price!</b>\n"

        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return self.send_message(message.strip(), disable_notification=True)

    def send_state_change(
        self,
        new_stage: str,
        market_id: Optional[int] = None,
        market_title: Optional[str] = None,
        price: Optional[float] = None,
        amount: Optional[float] = None,
        spread: Optional[float] = None,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None
    ) -> bool:
        """
        Send notification for state change (e.g., BUY_PLACED, SELL_PLACED).

        Args:
            new_stage: New bot stage
            market_id: Market ID (if applicable)
            market_title: Market title (if applicable)
            price: Order price (if applicable)
            amount: Order amount in USDT (if applicable)
            spread: Market spread (if applicable)
            best_bid: Best bid price (if applicable)
            best_ask: Best ask price (if applicable)

        Returns:
            True if sent successfully
        """
        stage_emoji = {
            'BUY_PLACED': '🟢',
            'SELL_PLACED': '🔴',
            'BUY_FILLED': '✅',
            'SELL_FILLED': '✅',
            'IDLE': '💤',
            'SCANNING': '🔍'
        }.get(new_stage, '📍')

        stage_name = new_stage.replace('_', ' ').title()

        message = f"{stage_emoji} <b>{stage_name}</b>\n\n"

        if market_id:
            message += f"📊 Market: #{market_id}\n"
        if market_title:
            title_short = market_title[:80] + "..." if len(market_title) > 80 else market_title
            message += f"   {title_short}\n\n"

        if price is not None:
            message += f"💵 Price: ${price:.4f}\n"
        if amount is not None:
            message += f"💰 Amount: ${amount:.2f}\n"

        # Add orderbook info if available (for BUY_PLACED, SELL_PLACED)
        if spread is not None and best_bid is not None and best_ask is not None:
            message += f"\n📈 <b>Orderbook:</b>\n"
            message += f"   • Spread: ${spread:.4f}\n"
            message += f"   • Best bid: ${best_bid:.4f}\n"
            message += f"   • Best ask: ${best_ask:.4f}\n"

        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return self.send_message(message.strip())

    def send_stop_loss(
        self,
        market_id: int,
        market_title: str,
        current_price: float,
        buy_price: float,
        pnl_percent: float,
        action: str = "triggered"
    ) -> bool:
        """
        Send stop-loss notification.

        Args:
            market_id: Market ID
            market_title: Market title
            current_price: Current market price
            buy_price: Original buy price
            pnl_percent: Current P&L percentage
            action: Action taken (e.g., "triggered", "executed")

        Returns:
            True if sent successfully
        """
        message = f"""
🚨 <b>STOP-LOSS {action.upper()}</b>

📊 Market: #{market_id}
   {market_title[:80]}

💵 <b>Prices:</b>
   • Buy price: ${buy_price:.4f}
   • Current price: ${current_price:.4f}

📉 <b>Loss:</b> {pnl_percent:.2f}%

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message.strip())

    def test_connection(self) -> bool:
        """
        Test Telegram connection by sending a test message.

        Returns:
            True if connection successful
        """
        if not self.enabled:
            logger.warning("Telegram notifications are not enabled")
            return False

        message = "✅ <b>Telegram Connection Test</b>\n\nBot notifications are working correctly!"

        result = self.send_message(message)

        if result:
            logger.info("✅ Telegram connection test successful")
        else:
            logger.error("❌ Telegram connection test failed")

        return result


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== Telegram Notifications Module Test ===")
    print()

    # Create notifier
    notifier = TelegramNotifier()

    if not notifier.enabled:
        print("⚠️  Telegram credentials not configured")
        print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        print()
        exit(0)

    print("Test 1: Connection test")
    notifier.test_connection()
    time.sleep(2)

    print("\nTest 2: Bot start notification")
    test_stats = {
        'total_trades': 5,
        'win_rate_percent': 60.0,
        'total_pnl_usdt': 12.50,
        'total_pnl_percent': 2.50
    }
    test_config = {
        'CAPITAL_MODE': 'percentage',
        'CAPITAL_PERCENTAGE': 90,
        'SCORING_PROFILE': 'production_farming',
        'ENABLE_STOP_LOSS': True
    }
    notifier.send_bot_start(test_stats, test_config, balance=100.0)
    time.sleep(2)

    print("\nTest 3: State change notification")
    notifier.send_state_change(
        new_stage='BUY_PLACED',
        market_id=12345,
        market_title='Will Bitcoin reach $100k by end of 2024?',
        price=0.6543,
        amount=50.0
    )
    time.sleep(2)

    print("\nTest 4: Heartbeat notification")
    notifier.send_heartbeat(
        stage='BUY_MONITORING',
        market_info={
            'market_id': 12345,
            'market_title': 'Will Bitcoin reach $100k by end of 2024?',
            'spread': 0.05,
            'best_bid': 0.65,
            'best_ask': 0.70
        },
        balance=50.0,
        position_value=50.0,
        outcome_side='YES'
    )
    time.sleep(2)

    print("\nTest 5: Stop-loss notification")
    notifier.send_stop_loss(
        market_id=12345,
        market_title='Will Bitcoin reach $100k by end of 2024?',
        current_price=0.55,
        buy_price=0.65,
        pnl_percent=-15.4
    )
    time.sleep(2)

    print("\nTest 6: Bot stop notification")
    test_logs = [
        "[INFO] Monitoring order...",
        "[INFO] Order filled successfully",
        "[INFO] Bot stopping...",
    ]
    notifier.send_bot_stop(test_stats, test_logs)

    print()
    print("✅ All tests complete! Check your Telegram chat for messages.")
