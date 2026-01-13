# -*- mode: python ; coding: utf-8 -*-
"""
Opinion Trading Bot - PyInstaller Build Specification
=====================================================

This spec file builds standalone executables for the Opinion Trading Bot GUI.

Usage:
    pyinstaller build_gui.spec

Output:
    dist/OpinionBot/    - Folder containing executable and dependencies

Platform-Specific Names:
    - Windows: OpinionBot.exe
    - Linux/macOS: OpinionBot

Build Requirements:
    - Python 3.10+
    - PyInstaller (pip install pyinstaller)
    - All dependencies from requirements.txt
"""

import sys
from pathlib import Path

block_cipher = None

# === Data Files ===
# Files to include in the distribution
datas = [
    ('.env.example', '.'),           # Credentials template
    ('README.md', '.'),              # Documentation
]

# Add optional files if they exist
optional_files = [
    ('version.txt', '.'),                # Version for update checker
    ('bonus_markets.txt.example', '.'),  # Bonus markets template
    ('LICENSE', '.'),                     # License file
    ('TELEGRAM_SETUP.md', '.'),          # Telegram setup guide
]

for src, dst in optional_files:
    if Path(src).exists():
        datas.append((src, dst))

# === Hidden Imports ===
# Modules that PyInstaller might miss during analysis
hiddenimports = [
    # Opinion SDK and dependencies
    'opinion_clob_sdk',
    'opinion_clob_sdk.client',
    'opinion_clob_sdk.api',

    # Web3 and blockchain
    'web3',
    'web3.providers',
    'web3.providers.rpc',
    'web3.providers.ipc',
    'web3.providers.eth_tester',
    'eth_account',
    'eth_utils',
    'eth_keys',

    # HTTP and networking
    'requests',
    'urllib3',

    # Environment management
    'dotenv',

    # Standard library (sometimes needed)
    'json',
    'decimal',
    'pathlib',
    'datetime',
    'threading',
    'subprocess',
    'tkinter',
    'tkinter.ttk',
    'tkinter.scrolledtext',
    'tkinter.messagebox',
    'tkinter.filedialog',

    # Bot modules (ensure all are included)
    'config',
    'config_loader',
    'config_validator',
    'gui_helpers',
    'api_client',
    'market_scanner',
    'order_manager',
    'position_tracker',
    'pnl_statistics',
    'telegram_notifications',
    'scoring',
    'utils',
    'logger_config',

    # Core modules
    'core.autonomous_bot',
    'core.position_validator',
    'core.position_recovery',
    'core.capital_manager',
    'core.state_manager',

    # Handlers
    'handlers.market_selector',
    'handlers.buy_handler',
    'handlers.sell_handler',

    # Monitoring
    'monitoring.buy_monitor',
    'monitoring.sell_monitor',
    'monitoring.liquidity_checker',

    # Strategies
    'strategies.pricing',
]

# === Analysis ===
a = Analysis(
    ['gui_launcher.py'],             # Entry point
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tests',                     # Don't package test suite
        'pytest',
        'unittest',
        'nose',
        'coverage',
        'black',
        'flake8',
        'mypy',
        'docs',                      # Don't package documentation folder
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# === PYZ Archive ===
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

# === Executable ===
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,            # One-folder mode (easier for updates)
    name='OpinionBot',                # Executable name
    debug=False,                      # No debug output
    bootloader_ignore_signals=False,
    strip=False,                      # Don't strip symbols
    upx=True,                         # Use UPX compression
    console=False,                    # GUI app - no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if Path('icon.ico').exists() else None,  # Optional icon
)

# === Collect Files ===
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OpinionBot',                # Output folder name
)

# === Platform-Specific Notes ===
"""
Build Output:
    dist/OpinionBot/
    ├── OpinionBot.exe (Windows) or OpinionBot (Linux/macOS)
    ├── _internal/              # Dependencies
    ├── .env.example            # Template
    ├── README.md              # Documentation
    └── version.txt            # Version info

Distribution:
    1. Copy entire OpinionBot/ folder
    2. Create ZIP: OpinionBot_Windows.zip (or _Linux, _macOS)
    3. Users extract and run OpinionBot.exe

Update Process:
    Users extract new ZIP to same folder - overwrites executables
    but preserves user files (.env, state.json, pnl_stats.json)
"""
