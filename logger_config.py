"""
Opinion Farming Bot - Logger Configuration Module
=================================================

Centralized logging setup for consistent logging across all bot modules.
Provides both console and file logging with different verbosity levels.

Usage:
    from logger_config import setup_logger
    logger = setup_logger(__name__)
    
    logger.debug("Detailed debug info")
    logger.info("Normal operation info")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical error")
"""

import logging
import logging.handlers
import sys
import os
from datetime import datetime
from pathlib import Path
from config import LOG_FILE, LOG_LEVEL


class PrintHandler(logging.Handler):
    """
    Custom logging handler that uses print() instead of stream.write().
    This ensures output goes to current sys.stdout (important for subprocess capture).

    Unlike StreamHandler which caches sys.stdout reference, print() always
    uses the current sys.stdout, making it work correctly when stdout is
    redirected after handler creation.
    """

    def emit(self, record):
        """
        Emit a record using print().

        Args:
            record: LogRecord to emit
        """
        try:
            msg = self.format(record)
            print(msg, flush=True)  # flush=True ensures immediate output for GUI capture
        except Exception:
            self.handleError(record)


class ColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds colors to console output.
    Makes it easier to spot warnings and errors in terminal.
    """

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }

    # Emoji indicators for quick visual scanning
    INDICATORS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }

    def format(self, record):
        # Add color and indicator based on log level
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        indicator = self.INDICATORS.get(record.levelname, '')

        # Format the message
        record.levelname = f"{color}{record.levelname}{reset}"
        record.msg = f"{indicator} {record.msg}"

        return super().format(record)


def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with console and file handlers.
    
    Args:
        name: Logger name (typically __name__ of the calling module)
        
    Returns:
        Configured logger instance
        
    Example:
        logger = setup_logger(__name__)
        logger.info("Bot started")
    """
    # Create logger
    logger = logging.getLogger(name)
    
    # Set base level from config
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Prevent duplicate handlers if logger already configured
    if logger.handlers:
        return logger
    
    # =========================================================================
    # CONSOLE HANDLER (using PrintHandler for subprocess capture)
    # =========================================================================
    # Uses print() instead of stream.write() to ensure output goes to current
    # sys.stdout (critical for GUI subprocess capture on Windows)
    console_handler = PrintHandler()
    console_handler.setLevel(logging.INFO)  # Console shows INFO and above

    console_format = ColoredFormatter(
        fmt='%(asctime)s │ %(levelname)-17s │ %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    
    # =========================================================================
    # FILE HANDLER (with daily rotation)
    # =========================================================================
    # Outputs to log file with full details (no colors)
    # Rotates logs daily at midnight, keeping logs organized by date

    # Ensure log file is in logs directory
    log_path = Path(LOG_FILE)
    if log_path.parent == Path('.'):
        # If LOG_FILE is just a filename, put it in logs/ directory
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        log_filename = logs_dir / log_path.name
    else:
        # If LOG_FILE already has a directory, use it and ensure directory exists
        log_filename = log_path
        log_filename.parent.mkdir(parents=True, exist_ok=True)

    # TimedRotatingFileHandler rotates logs at midnight each day
    # when='midnight' - rotate at midnight
    # interval=1 - every 1 day
    # backupCount=30 - keep 30 days of logs (optional, 0=keep all)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_filename,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # File captures everything

    # Set suffix for rotated files to include date
    file_handler.suffix = '%Y-%m-%d.log'

    file_format = logging.Formatter(
        fmt='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


def log_section_header(logger: logging.Logger, title: str, char: str = "="):
    """
    Log a visually distinct section header.
    Useful for marking major phases of bot operation.
    
    Args:
        logger: Logger instance
        title: Section title
        char: Character to use for the border (default: =)
        
    Example:
        log_section_header(logger, "MARKET SCANNER")
        # Outputs:
        # ==========================================
        # MARKET SCANNER
        # ==========================================
    """
    width = 50
    border = char * width
    logger.info("")
    logger.info(border)
    logger.info(title.center(width))
    logger.info(border)


def log_key_value(logger: logging.Logger, key: str, value, indent: int = 3):
    """
    Log a key-value pair with consistent formatting.
    
    Args:
        logger: Logger instance
        key: Label/key
        value: Value to display
        indent: Number of spaces to indent (default: 3)
        
    Example:
        log_key_value(logger, "Market ID", 813)
        # Outputs: "   Market ID: 813"
    """
    spaces = " " * indent
    logger.info(f"{spaces}{key}: {value}")


def log_table_row(logger: logging.Logger, columns: list, widths: list):
    """
    Log a formatted table row.
    
    Args:
        logger: Logger instance
        columns: List of column values
        widths: List of column widths
        
    Example:
        log_table_row(logger, ["813", "BTC 100k?", "15.2%"], [6, 20, 8])
    """
    row = "│"
    for col, width in zip(columns, widths):
        row += f" {str(col):<{width}} │"
    logger.info(row)


def log_startup_banner(logger: logging.Logger, stage_name: str, version: str = "1.0"):
    """
    Log the bot startup banner.
    
    Args:
        logger: Logger instance
        stage_name: Name of the current stage
        version: Version number
    """
    logger.info("")
    logger.info("=" * 50)
    logger.info("OPINION FARMING BOT".center(50))
    logger.info(f"{stage_name} v{version}".center(50))
    logger.info("=" * 50)
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")


def log_order_details(logger: logging.Logger, order_data: dict):
    """
    Log order details in a structured format.
    
    Args:
        logger: Logger instance
        order_data: Dictionary with order details
    """
    logger.info("📋 Order Details:")
    logger.info(f"   Order ID: {order_data.get('order_id', 'N/A')}")
    logger.info(f"   Market: #{order_data.get('market_id', 'N/A')}")
    logger.info(f"   Side: {order_data.get('side', 'N/A')}")
    logger.info(f"   Price: ${order_data.get('price', 0):.4f}")
    logger.info(f"   Amount: {order_data.get('amount', 0):.2f} USDT")
    logger.info(f"   Status: {order_data.get('status', 'N/A')}")


def log_pnl_summary(logger: logging.Logger, pnl_data: dict):
    """
    Log P&L summary in a formatted block.
    
    Args:
        logger: Logger instance
        pnl_data: Dictionary with P&L details
    """
    logger.info("")
    logger.info("=" * 50)
    logger.info("POSITION CLOSED - P&L SUMMARY".center(50))
    logger.info("=" * 50)
    logger.info("")
    logger.info("📊 BUY Side:")
    logger.info(f"   Amount: {pnl_data.get('buy_tokens', 0):.4f} tokens")
    logger.info(f"   Avg price: ${pnl_data.get('buy_price', 0):.4f}")
    logger.info(f"   Total cost: {pnl_data.get('buy_cost', 0):.2f} USDT")
    logger.info("")
    logger.info("📊 SELL Side:")
    logger.info(f"   Amount: {pnl_data.get('sell_tokens', 0):.4f} tokens")
    logger.info(f"   Avg price: ${pnl_data.get('sell_price', 0):.4f}")
    logger.info(f"   Total proceeds: {pnl_data.get('sell_proceeds', 0):.2f} USDT")
    logger.info("")
    
    pnl = pnl_data.get('pnl', 0)
    pnl_pct = pnl_data.get('pnl_percent', 0)
    pnl_sign = "+" if pnl >= 0 else ""
    
    logger.info("💰 Profit & Loss:")
    logger.info(f"   Net P&L: {pnl_sign}{pnl:.2f} USDT ({pnl_sign}{pnl_pct:.2f}%)")
    logger.info("")


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    # Test the logger
    test_logger = setup_logger("test")
    
    log_startup_banner(test_logger, "Logger Test")
    
    test_logger.debug("This is a debug message")
    test_logger.info("This is an info message")
    test_logger.warning("This is a warning message")
    test_logger.error("This is an error message")
    
    log_section_header(test_logger, "TEST SECTION")
    log_key_value(test_logger, "Test Key", "Test Value")
    
    print("\n✅ Logger test complete! Check opinion_farming_bot.log for file output.")
