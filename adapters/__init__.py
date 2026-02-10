"""
Adapters Package
================

Platform adapters for multi-platform prediction market trading.

This package contains abstract base classes and concrete implementations
for different prediction market platforms (Opinion.trade, Hyperliquid, etc).

The adapter pattern allows the bot to support multiple platforms with
minimal code changes - just swap the adapter.

Available Adapters:
-------------------
- base.PredictionMarketClient: Abstract base class defining the interface
- (Future) opinion_adapter.OpinionAdapter: Opinion.trade implementation
- (Future) hyperliquid_adapter.HyperliquidAdapter: Hyperliquid implementation
"""

from adapters.base import PredictionMarketClient

__all__ = ['PredictionMarketClient']
