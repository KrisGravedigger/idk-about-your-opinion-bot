"""
PnL Statistics Manager
======================

Manages persistent P&L statistics in a separate file from state.json.
This ensures statistics are preserved even when state.json is deleted for recovery.

The statistics file tracks:
- Total number of trades (wins/losses)
- Total P&L in USDT and percentage
- Win rate
- Consecutive losses (for risk management)
- Session history

Usage:
    from pnl_statistics import PnLStatistics

    stats = PnLStatistics()
    stats.update_after_trade(pnl_usdt=5.50, is_win=True)
    stats.display_summary()
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from decimal import Decimal
from logger_config import setup_logger
from utils import get_timestamp, safe_float

logger = setup_logger(__name__)


class PnLStatistics:
    """
    Manages P&L statistics persistence and tracking.

    Attributes:
        stats_file: Path to statistics file (default: pnl_stats.json)
    """

    def __init__(self, stats_file: str = "pnl_stats.json"):
        """
        Initialize PnL Statistics Manager.

        Args:
            stats_file: Path to statistics file
        """
        self.stats_file = Path(stats_file)
        self.stats = self.load_stats()
        logger.debug(f"PnLStatistics initialized: {self.stats_file}")

    def load_stats(self) -> Dict[str, Any]:
        """
        Load statistics from file, return default if missing.

        Returns:
            Statistics dictionary
        """
        if not self.stats_file.exists():
            logger.info("No statistics file found, initializing fresh stats")
            return self._initialize_stats()

        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                stats = json.load(f)

            logger.debug(f"✅ Statistics loaded from {self.stats_file}")
            logger.debug(f"   Total trades: {stats.get('total_trades', 0)}")
            logger.debug(f"   Total P&L: ${stats.get('total_pnl_usdt', 0):.2f}")

            # Ensure all required fields exist (for backwards compatibility)
            default_stats = self._initialize_stats()
            for key, value in default_stats.items():
                if key not in stats:
                    stats[key] = value

            return stats

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading statistics file: {e}")
            logger.warning("Initializing fresh statistics")
            return self._initialize_stats()

    def save_stats(self) -> bool:
        """
        Save statistics to file with pretty JSON formatting.

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Update timestamp
            self.stats['last_updated_at'] = get_timestamp()

            # Save with pretty formatting
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2, ensure_ascii=False)

            logger.debug(f"Statistics saved to {self.stats_file}")
            return True

        except IOError as e:
            logger.error(f"Error saving statistics: {e}")
            return False

    def _initialize_stats(self) -> Dict[str, Any]:
        """
        Create fresh statistics structure.

        Returns:
            New statistics dictionary with default values
        """
        timestamp = get_timestamp()

        stats = {
            "version": "1.0",
            "created_at": timestamp,
            "last_updated_at": timestamp,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "consecutive_losses": 0,
            "total_pnl_usdt": 0.0,
            "total_pnl_percent": 0.0,
            "win_rate_percent": 0.0,
            "best_trade_usdt": 0.0,
            "worst_trade_usdt": 0.0,
            "avg_win_usdt": 0.0,
            "avg_loss_usdt": 0.0
        }

        logger.info("✅ Fresh statistics initialized")
        return stats

    def update_after_trade(self, pnl_usdt: float, pnl_percent: float = None) -> None:
        """
        Update statistics after a completed trade.

        Args:
            pnl_usdt: Profit/loss in USDT
            pnl_percent: Profit/loss percentage (optional)
        """
        is_win = pnl_usdt > 0

        self.stats['total_trades'] += 1

        if is_win:
            self.stats['wins'] += 1
            self.stats['consecutive_losses'] = 0  # Reset streak

            # Update average win
            current_avg_win = self.stats.get('avg_win_usdt', 0.0)
            wins = self.stats['wins']
            self.stats['avg_win_usdt'] = (
                (current_avg_win * (wins - 1) + pnl_usdt) / wins
            )
        else:
            self.stats['losses'] += 1
            self.stats['consecutive_losses'] += 1

            # Update average loss
            current_avg_loss = self.stats.get('avg_loss_usdt', 0.0)
            losses = self.stats['losses']
            self.stats['avg_loss_usdt'] = (
                (current_avg_loss * (losses - 1) + pnl_usdt) / losses
            )

        # Update total P&L
        self.stats['total_pnl_usdt'] += pnl_usdt

        # Update best/worst trade
        if pnl_usdt > self.stats.get('best_trade_usdt', 0):
            self.stats['best_trade_usdt'] = pnl_usdt
        if pnl_usdt < self.stats.get('worst_trade_usdt', 0):
            self.stats['worst_trade_usdt'] = pnl_usdt

        # Calculate average P&L percentage
        if self.stats['total_trades'] > 0:
            self.stats['total_pnl_percent'] = (
                self.stats['total_pnl_usdt'] / self.stats['total_trades']
            )

        # Calculate win rate
        if self.stats['total_trades'] > 0:
            self.stats['win_rate_percent'] = (
                (self.stats['wins'] / self.stats['total_trades']) * 100
            )

        # Save immediately
        self.save_stats()

        logger.debug(f"Statistics updated: {'+' if is_win else ''}{pnl_usdt:.2f} USDT")

    def get_summary(self) -> Dict[str, Any]:
        """
        Get current statistics summary.

        Returns:
            Dictionary with formatted statistics
        """
        return {
            'total_trades': self.stats['total_trades'],
            'wins': self.stats['wins'],
            'losses': self.stats['losses'],
            'consecutive_losses': self.stats['consecutive_losses'],
            'total_pnl_usdt': self.stats['total_pnl_usdt'],
            'avg_pnl_per_trade': self.stats['total_pnl_percent'],
            'win_rate_percent': self.stats['win_rate_percent'],
            'best_trade_usdt': self.stats.get('best_trade_usdt', 0.0),
            'worst_trade_usdt': self.stats.get('worst_trade_usdt', 0.0),
            'avg_win_usdt': self.stats.get('avg_win_usdt', 0.0),
            'avg_loss_usdt': self.stats.get('avg_loss_usdt', 0.0)
        }

    def display_summary(self, logger_instance=None) -> None:
        """
        Display statistics summary in formatted output.

        Args:
            logger_instance: Optional logger instance (uses module logger if None)
        """
        log = logger_instance or logger

        log.info("")
        log.info("=" * 60)
        log.info("P&L STATISTICS SUMMARY".center(60))
        log.info("=" * 60)

        stats = self.stats

        log.info(f"   Total trades: {stats['total_trades']}")
        log.info(f"   Wins: {stats['wins']} | Losses: {stats['losses']}")
        log.info(f"   Win rate: {stats['win_rate_percent']:.1f}%")

        pnl_sign = "+" if stats['total_pnl_usdt'] >= 0 else ""
        log.info(f"   Total P&L: {pnl_sign}${stats['total_pnl_usdt']:.2f}")
        log.info(f"   Avg P&L per trade: {pnl_sign}${stats['total_pnl_percent']:.2f}")

        if stats.get('best_trade_usdt', 0) != 0:
            log.info(f"   Best trade: +${stats['best_trade_usdt']:.2f}")
        if stats.get('worst_trade_usdt', 0) != 0:
            log.info(f"   Worst trade: ${stats['worst_trade_usdt']:.2f}")

        if stats.get('avg_win_usdt', 0) > 0:
            log.info(f"   Avg win: +${stats['avg_win_usdt']:.2f}")
        if stats.get('avg_loss_usdt', 0) < 0:
            log.info(f"   Avg loss: ${stats['avg_loss_usdt']:.2f}")

        if stats.get('consecutive_losses', 0) > 0:
            log.info(f"   ⚠️  Consecutive losses: {stats['consecutive_losses']}")

        log.info("=" * 60)
        log.info("")

    def reset_stats(self) -> None:
        """Reset all statistics to initial values (use with caution!)."""
        logger.warning("⚠️  Resetting all P&L statistics!")
        self.stats = self._initialize_stats()
        self.save_stats()
        logger.info("✅ Statistics reset complete")


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== PnL Statistics Module Test ===")
    print()

    stats = PnLStatistics("test_pnl_stats.json")

    # Simulate some trades
    print("Test 1: Simulating trades...")
    stats.update_after_trade(pnl_usdt=5.50)   # Win
    stats.update_after_trade(pnl_usdt=-2.30)  # Loss
    stats.update_after_trade(pnl_usdt=8.20)   # Win
    stats.update_after_trade(pnl_usdt=-1.10)  # Loss
    stats.update_after_trade(pnl_usdt=3.40)   # Win

    print("✅ Trades simulated")
    print()

    # Display summary
    print("Test 2: Display summary")
    stats.display_summary()

    # Get summary as dict
    print("Test 3: Get summary as dictionary")
    summary = stats.get_summary()
    print(f"   Total trades: {summary['total_trades']}")
    print(f"   Total P&L: ${summary['total_pnl_usdt']:.2f}")
    print(f"   Win rate: {summary['win_rate_percent']:.1f}%")
    print()

    # Cleanup test file
    import os
    if os.path.exists("test_pnl_stats.json"):
        os.remove("test_pnl_stats.json")
        print("✅ Test file cleaned up")

    print()
    print("✅ PnL Statistics tests complete!")
