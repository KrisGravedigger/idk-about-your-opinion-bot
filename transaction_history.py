"""
Transaction History Module
==========================

Persists a detailed history of all transactions (BUY and SELL orders).
This provides an independent audit trail separate from state.json and helps
debug API inconsistencies.

Features:
- Records every BUY and SELL transaction with full details
- Timestamped entries for audit trail
- Helps reconcile positions when API returns inconsistent data
- Supports querying by market_id, date range, etc.

Usage:
    from transaction_history import TransactionHistory

    history = TransactionHistory()
    history.record_buy(
        market_id=3039,
        token_id="495351...",
        shares=125.30,
        price=0.443,
        amount_usdt=55.52,
        order_id="abc123"
    )
    history.display_summary()
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from logger_config import setup_logger
from utils import get_timestamp, safe_float

logger = setup_logger(__name__)


class TransactionHistory:
    """
    Manages persistent transaction history tracking.

    Attributes:
        history_file: Path to history file (default: transaction_history.json)
    """

    def __init__(self, history_file: str = "transaction_history.json"):
        """
        Initialize Transaction History Manager.

        Args:
            history_file: Path to history file
        """
        self.history_file = Path(history_file)
        self.transactions = self.load_history()
        logger.debug(f"TransactionHistory initialized: {self.history_file}")

    def load_history(self) -> List[Dict[str, Any]]:
        """
        Load transaction history from file.

        Returns:
            List of transaction dictionaries
        """
        if not self.history_file.exists():
            logger.info("No transaction history found, initializing fresh history")
            return []

        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            transactions = data.get('transactions', [])

            logger.debug(f"✅ History loaded: {len(transactions)} transaction(s)")
            return transactions

        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading history file: {e}")
            logger.warning("Initializing fresh history")
            return []

    def save_history(self) -> bool:
        """
        Save transaction history to file.

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            data = {
                'version': '1.0',
                'last_updated': get_timestamp(),
                'total_transactions': len(self.transactions),
                'transactions': self.transactions
            }

            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"History saved: {len(self.transactions)} transaction(s)")
            return True

        except IOError as e:
            logger.error(f"Error saving history: {e}")
            return False

    def record_buy(
        self,
        market_id: int,
        market_title: str,
        token_id: str,
        shares: float,
        price: float,
        amount_usdt: float,
        order_id: str,
        outcome: str = "YES",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a BUY transaction.

        Args:
            market_id: Market ID
            market_title: Market title/description
            token_id: Token ID (long hex string)
            shares: Number of shares purchased
            price: Average fill price per share
            amount_usdt: Total USDT spent
            order_id: Order ID from API
            outcome: YES or NO (default: YES)
            metadata: Optional additional data (e.g., slippage, fees)
        """
        transaction = {
            'transaction_id': f"buy_{order_id}_{get_timestamp()}",
            'type': 'BUY',
            'timestamp': get_timestamp(),
            'market_id': market_id,
            'market_title': market_title,
            'token_id': token_id[:20] + "...",  # Truncate for readability
            'token_id_full': token_id,
            'outcome': outcome,
            'shares': round(shares, 4),
            'price': round(price, 6),
            'amount_usdt': round(amount_usdt, 2),
            'order_id': order_id,
            'metadata': metadata or {}
        }

        self.transactions.append(transaction)
        self.save_history()

        logger.debug(
            f"📝 BUY recorded: {shares:.4f} {outcome} @ ${price:.4f} "
            f"= ${amount_usdt:.2f} (market #{market_id})"
        )

    def record_sell(
        self,
        market_id: int,
        market_title: str,
        token_id: str,
        shares: float,
        price: float,
        amount_usdt: float,
        order_id: str,
        outcome: str = "YES",
        pnl_usdt: Optional[float] = None,
        pnl_percent: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a SELL transaction.

        Args:
            market_id: Market ID
            market_title: Market title/description
            token_id: Token ID (long hex string)
            shares: Number of shares sold
            price: Average fill price per share
            amount_usdt: Total USDT received
            order_id: Order ID from API
            outcome: YES or NO (default: YES)
            pnl_usdt: Profit/loss in USDT (optional)
            pnl_percent: Profit/loss percentage (optional)
            metadata: Optional additional data
        """
        transaction = {
            'transaction_id': f"sell_{order_id}_{get_timestamp()}",
            'type': 'SELL',
            'timestamp': get_timestamp(),
            'market_id': market_id,
            'market_title': market_title,
            'token_id': token_id[:20] + "...",  # Truncate for readability
            'token_id_full': token_id,
            'outcome': outcome,
            'shares': round(shares, 4),
            'price': round(price, 6),
            'amount_usdt': round(amount_usdt, 2),
            'order_id': order_id,
            'pnl_usdt': round(pnl_usdt, 2) if pnl_usdt is not None else None,
            'pnl_percent': round(pnl_percent, 2) if pnl_percent is not None else None,
            'metadata': metadata or {}
        }

        self.transactions.append(transaction)
        self.save_history()

        pnl_str = f", P&L: ${pnl_usdt:+.2f}" if pnl_usdt is not None else ""
        logger.debug(
            f"📝 SELL recorded: {shares:.4f} {outcome} @ ${price:.4f} "
            f"= ${amount_usdt:.2f}{pnl_str} (market #{market_id})"
        )

    def get_transactions_for_market(self, market_id: int) -> List[Dict[str, Any]]:
        """
        Get all transactions for a specific market.

        Args:
            market_id: Market ID to filter by

        Returns:
            List of transactions for that market
        """
        return [t for t in self.transactions if t.get('market_id') == market_id]

    def get_recent_transactions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most recent transactions.

        Args:
            limit: Maximum number of transactions to return

        Returns:
            List of recent transactions (newest first)
        """
        return sorted(
            self.transactions,
            key=lambda t: t.get('timestamp', ''),
            reverse=True
        )[:limit]

    def calculate_market_pnl(self, market_id: int) -> Dict[str, float]:
        """
        Calculate total P&L for a specific market.

        Args:
            market_id: Market ID

        Returns:
            Dictionary with buy_cost, sell_proceeds, pnl
        """
        market_txns = self.get_transactions_for_market(market_id)

        buy_cost = sum(
            t['amount_usdt'] for t in market_txns
            if t['type'] == 'BUY'
        )

        sell_proceeds = sum(
            t['amount_usdt'] for t in market_txns
            if t['type'] == 'SELL'
        )

        pnl = sell_proceeds - buy_cost

        return {
            'buy_cost': buy_cost,
            'sell_proceeds': sell_proceeds,
            'pnl': pnl,
            'pnl_percent': (pnl / buy_cost * 100) if buy_cost > 0 else 0
        }

    def display_summary(self, limit: int = 10) -> None:
        """
        Display transaction history summary.

        Args:
            limit: Number of recent transactions to show
        """
        if not self.transactions:
            logger.info("No transactions recorded yet")
            return

        logger.info("")
        logger.info("=" * 70)
        logger.info("TRANSACTION HISTORY".center(70))
        logger.info("=" * 70)
        logger.info(f"Total transactions: {len(self.transactions)}")
        logger.info("")

        recent = self.get_recent_transactions(limit)

        logger.info(f"Most recent {len(recent)} transaction(s):")
        logger.info("")

        for txn in recent:
            txn_type = txn['type']
            emoji = "📈" if txn_type == 'BUY' else "📉"
            timestamp = txn.get('timestamp', 'N/A')
            market_id = txn.get('market_id', '?')
            shares = txn.get('shares', 0)
            price = txn.get('price', 0)
            amount = txn.get('amount_usdt', 0)
            outcome = txn.get('outcome', 'YES')

            logger.info(
                f"{emoji} [{timestamp}] {txn_type:4s} | "
                f"Market #{market_id:4d} | "
                f"{shares:8.2f} {outcome} @ ${price:.4f} = ${amount:7.2f}"
            )

            # Show P&L for SELL transactions
            if txn_type == 'SELL' and txn.get('pnl_usdt') is not None:
                pnl = txn['pnl_usdt']
                pnl_pct = txn.get('pnl_percent', 0)
                pnl_sign = "+" if pnl >= 0 else ""
                logger.info(f"       P&L: {pnl_sign}${pnl:.2f} ({pnl_sign}{pnl_pct:.2f}%)")

        logger.info("=" * 70)
        logger.info("")

    def display_market_summary(self, market_id: int) -> None:
        """
        Display summary for a specific market.

        Args:
            market_id: Market ID to summarize
        """
        txns = self.get_transactions_for_market(market_id)

        if not txns:
            logger.info(f"No transactions found for market #{market_id}")
            return

        pnl_data = self.calculate_market_pnl(market_id)

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"MARKET #{market_id} SUMMARY".center(60))
        logger.info("=" * 60)
        logger.info(f"   Total transactions: {len(txns)}")
        logger.info(f"   Total buy cost: ${pnl_data['buy_cost']:.2f}")
        logger.info(f"   Total sell proceeds: ${pnl_data['sell_proceeds']:.2f}")

        pnl_sign = "+" if pnl_data['pnl'] >= 0 else ""
        logger.info(
            f"   Net P&L: {pnl_sign}${pnl_data['pnl']:.2f} "
            f"({pnl_sign}{pnl_data['pnl_percent']:.2f}%)"
        )
        logger.info("=" * 60)
        logger.info("")

    def reset_history(self) -> None:
        """Reset transaction history (use with caution!)."""
        logger.warning("⚠️  Resetting transaction history!")
        self.transactions = []
        self.save_history()
        logger.info("✅ History reset complete")


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== Transaction History Module Test ===")
    print()

    history = TransactionHistory("test_transaction_history.json")

    # Simulate some transactions
    print("Test 1: Recording transactions...")
    history.record_buy(
        market_id=3039,
        market_title="Israel strikes Iran by March 31, 2026?",
        token_id="49535181559182780686886024535845995911691753820290126235145703538207021398285",
        shares=125.30,
        price=0.443,
        amount_usdt=55.52,
        order_id="test_buy_123"
    )

    history.record_sell(
        market_id=3039,
        market_title="Israel strikes Iran by March 31, 2026?",
        token_id="49535181559182780686886024535845995911691753820290126235145703538207021398285",
        shares=125.30,
        price=0.446,
        amount_usdt=55.88,
        order_id="test_sell_456",
        pnl_usdt=0.36,
        pnl_percent=0.65
    )

    print("✅ Transactions recorded")
    print()

    # Display summary
    print("Test 2: Display summary")
    history.display_summary()

    # Display market summary
    print("Test 3: Market summary")
    history.display_market_summary(3039)

    # Cleanup test file
    import os
    if os.path.exists("test_transaction_history.json"):
        os.remove("test_transaction_history.json")
        print("✅ Test file cleaned up")

    print()
    print("✅ Transaction History tests complete!")
