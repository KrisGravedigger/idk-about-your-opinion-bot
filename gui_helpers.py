"""
GUI Helper Functions
====================

Shared utility functions for the Bot Launcher GUI.
Extracted from gui_launcher.py to reduce code duplication.
"""

from tkinter import messagebox
from typing import List, Tuple
import json
from pathlib import Path


def toggle_field_visibility(show_var, entry_widget):
    """
    Toggle password field visibility (show/hide).

    Args:
        show_var: BooleanVar controlling visibility
        entry_widget: Entry widget to toggle
    """
    entry_widget.config(show="" if show_var.get() else "*")


def toggle_widget_state(enable_var, *widgets):
    """
    Enable or disable widgets based on boolean variable.

    Args:
        enable_var: BooleanVar controlling enabled state
        *widgets: Variable number of widgets to toggle
    """
    state = 'normal' if enable_var.get() else 'disabled'
    for widget in widgets:
        widget.config(state=state)


def show_validation_errors(title: str, prefix: str, errors: List[str]) -> None:
    """
    Display validation errors in a message box.

    Args:
        title: Dialog title
        prefix: Message prefix (e.g., "Cannot start bot")
        errors: List of error messages
    """
    if not errors:
        return

    error_msg = f"{prefix}:\n\n" + "\n".join(f"• {err}" for err in errors)
    messagebox.showerror(title, error_msg)


def show_validation_warnings(title: str, warnings: List[str], action: str = "Continue") -> bool:
    """
    Display validation warnings and ask user to confirm.

    Args:
        title: Dialog title
        warnings: List of warning messages
        action: Action description (e.g., "Start bot", "Continue")

    Returns:
        True if user wants to proceed, False otherwise
    """
    if not warnings:
        return True

    warning_msg = "Configuration warnings:\n\n" + "\n".join(f"• {warn}" for warn in warnings)
    warning_msg += f"\n\n{action} anyway?"
    return messagebox.askyesno(title, warning_msg)


def validate_and_warn(config_data: dict, validate_func, operation: str = "Continue") -> bool:
    """
    Validate configuration, show errors/warnings, return True if safe to proceed.

    Args:
        config_data: Configuration dictionary to validate
        validate_func: Validation function that returns (is_valid, errors, warnings)
        operation: Operation description for warning dialog

    Returns:
        True if validation passed and user confirmed warnings, False otherwise
    """
    is_valid, errors, warnings = validate_func(config_data)

    if not is_valid:
        show_validation_errors("Invalid Configuration",
                               "Cannot proceed with invalid configuration",
                               errors)
        return False

    if warnings:
        return show_validation_warnings("Configuration Warnings", warnings, operation)

    return True


def load_json_file(filepath: Path) -> dict:
    """
    Load JSON file with error handling.

    Args:
        filepath: Path to JSON file

    Returns:
        Dictionary with loaded data, or empty dict on error

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json_file(filepath: Path, data: dict) -> None:
    """
    Save dictionary to JSON file.

    Args:
        filepath: Path to save file
        data: Dictionary to save
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def format_timestamp_log(timestamp: str, message: str, tag: str = None) -> Tuple[str, str]:
    """
    Format log message with timestamp.

    Args:
        timestamp: Timestamp string (e.g., "14:30:45")
        message: Log message
        tag: Optional tag for coloring

    Returns:
        Tuple of (timestamp_part, message_part) for appending to text widget
    """
    timestamp_part = f"[{timestamp}] "
    return timestamp_part, message


def truncate_text(text: str, max_length: int = 10, suffix: str = "...") -> str:
    """
    Truncate long text for display (e.g., API keys).

    Args:
        text: Text to truncate
        max_length: Maximum length before truncation
        suffix: Suffix to add when truncated

    Returns:
        Truncated text

    Example:
        >>> truncate_text("verylongapikey123456", 10)
        'verylonga...'
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + suffix


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB", "234 KB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"
