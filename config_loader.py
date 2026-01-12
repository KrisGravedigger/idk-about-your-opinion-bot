"""
Configuration Loader with Smart Merging
========================================

Loads configuration from multiple sources with priority:
1. config.py (defaults)
2. bot_config.json (GUI overrides) - if exists
3. Environment variables (highest priority)

Returns a module-like object with all config values.

Usage:
    from config_loader import config

    # Access values like original config.py
    capital_mode = config.CAPITAL_MODE
    api_key = config.API_KEY
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
import config as config_py  # Import original config.py
from dotenv import load_dotenv

# Reload environment variables
load_dotenv(override=True)


class ConfigLoader:
    """Dynamic configuration object that merges multiple sources."""

    def __init__(self):
        """Initialize by merging all config sources."""
        # Load defaults from config.py
        self._load_defaults()

        # Merge bot_config.json if exists
        self._merge_json_config()

        # Override with environment variables (credentials only)
        self._merge_env_vars()

    def _load_defaults(self):
        """Load all values from config.py."""
        for attr in dir(config_py):
            if not attr.startswith('_'):
                setattr(self, attr, getattr(config_py, attr))

    def _merge_json_config(self):
        """Merge values from bot_config.json if exists."""
        config_file = Path("bot_config.json")
        if not config_file.exists():
            return

        try:
            with open(config_file, 'r') as f:
                json_config = json.load(f)

            # Merge values - JSON keys are lowercase, config keys are UPPERCASE
            for key, value in json_config.items():
                # Convert to uppercase for config attribute names
                upper_key = key.upper()

                # Only set if attribute exists in config.py (prevent arbitrary attributes)
                if hasattr(self, upper_key):
                    # Special handling for nested dicts
                    if isinstance(value, dict) and hasattr(getattr(self, upper_key), '__dict__'):
                        # Merge dict values
                        current = getattr(self, upper_key)
                        if isinstance(current, dict):
                            current.update(value)
                    else:
                        setattr(self, upper_key, value)

            # Special handling for scoring_profile - update DEFAULT_SCORING_PROFILE
            if 'scoring_profile' in json_config:
                self.DEFAULT_SCORING_PROFILE = json_config['scoring_profile']

            # Special handling for custom scoring_weights
            if 'scoring_weights' in json_config and json_config.get('scoring_profile') == 'custom':
                # Create or update custom profile in SCORING_PROFILES
                if not hasattr(self, 'SCORING_PROFILES') or not isinstance(self.SCORING_PROFILES, dict):
                    self.SCORING_PROFILES = {}

                self.SCORING_PROFILES['custom'] = {
                    'description': 'Custom profile from GUI',
                    'weights': json_config['scoring_weights'],
                    'bonus_multiplier': json_config.get('bonus_multiplier', 1.0),
                    'invert_spread': False,
                }

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load bot_config.json: {e}")

    def _merge_env_vars(self):
        """Override with environment variables (credentials)."""
        # API & Blockchain credentials
        if os.getenv("API_KEY"):
            self.API_KEY = os.getenv("API_KEY")

        if os.getenv("PRIVATE_KEY"):
            self.PRIVATE_KEY = os.getenv("PRIVATE_KEY")

        if os.getenv("MULTI_SIG_ADDRESS"):
            self.MULTI_SIG_ADDRESS = os.getenv("MULTI_SIG_ADDRESS").strip() or None

        if os.getenv("RPC_URL"):
            self.RPC_URL = os.getenv("RPC_URL")

        # Telegram credentials
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

        if os.getenv("TELEGRAM_CHAT_ID"):
            self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value like a dict."""
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access."""
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        """Allow 'in' operator."""
        return hasattr(self, key)

    def get_scoring_profile(self, profile_name: str = None):
        """
        Get scoring profile by name from merged config.

        Args:
            profile_name: Name of profile (or None for default)

        Returns:
            Profile dict

        Raises:
            ValueError: If profile doesn't exist
        """
        if profile_name is None:
            profile_name = self.DEFAULT_SCORING_PROFILE

        if not hasattr(self, 'SCORING_PROFILES') or profile_name not in self.SCORING_PROFILES:
            available = ', '.join(self.SCORING_PROFILES.keys()) if hasattr(self, 'SCORING_PROFILES') else 'none'
            raise ValueError(
                f"Unknown scoring profile: '{profile_name}'\n"
                f"Available profiles: {available}"
            )

        return self.SCORING_PROFILES[profile_name]


# Create singleton instance
config = ConfigLoader()


def save_config_to_json(config_dict: Dict[str, Any], filepath: str = "bot_config.json"):
    """
    Save configuration to JSON file.

    Args:
        config_dict: Dictionary with configuration values (lowercase keys)
        filepath: Path to save JSON file

    Note:
        This function does NOT save credentials (API keys, private keys).
        Credentials should remain in .env file.
    """
    # Keys to exclude (credentials that should stay in .env)
    excluded_keys = {
        'api_key', 'private_key', 'multi_sig_address',
        'telegram_bot_token', 'telegram_chat_id', 'rpc_url'
    }

    # Filter out credentials
    filtered_config = {
        k: v for k, v in config_dict.items()
        if k.lower() not in excluded_keys
    }

    # Save to file
    config_path = Path(filepath)
    with open(config_path, 'w') as f:
        json.dump(filtered_config, f, indent=2)

    return config_path


def save_env_vars(env_vars: Dict[str, str], filepath: str = ".env"):
    """
    Save credentials to .env file.

    Args:
        env_vars: Dictionary with environment variables
        filepath: Path to .env file
    """
    env_path = Path(filepath)

    # Read existing .env if it exists
    existing_vars = {}
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_vars[key.strip()] = value.strip()

    # Update with new values
    existing_vars.update(env_vars)

    # Write back to file
    with open(env_path, 'w') as f:
        f.write("# Opinion Trading Bot Configuration\n")
        f.write("# Generated by GUI Configurator\n\n")

        # Write credentials
        if 'API_KEY' in existing_vars:
            f.write(f"API_KEY={existing_vars['API_KEY']}\n")
        if 'PRIVATE_KEY' in existing_vars:
            f.write(f"PRIVATE_KEY={existing_vars['PRIVATE_KEY']}\n")
        if 'MULTI_SIG_ADDRESS' in existing_vars:
            f.write(f"MULTI_SIG_ADDRESS={existing_vars['MULTI_SIG_ADDRESS']}\n")
        if 'RPC_URL' in existing_vars:
            f.write(f"RPC_URL={existing_vars['RPC_URL']}\n")

        f.write("\n# Telegram Notifications\n")
        if 'TELEGRAM_BOT_TOKEN' in existing_vars:
            f.write(f"TELEGRAM_BOT_TOKEN={existing_vars['TELEGRAM_BOT_TOKEN']}\n")
        if 'TELEGRAM_CHAT_ID' in existing_vars:
            f.write(f"TELEGRAM_CHAT_ID={existing_vars['TELEGRAM_CHAT_ID']}\n")

    # Set restrictive permissions on .env file (Unix-like systems)
    try:
        env_path.chmod(0o600)
    except:
        pass  # Windows doesn't support chmod

    return env_path
