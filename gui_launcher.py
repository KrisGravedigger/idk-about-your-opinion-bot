"""
Opinion Trading Bot - GUI Launcher & Configurator
=================================================

Graphical interface for configuring and launching the trading bot.

Features:
- 6-tab configuration interface
- Simple bot launcher (subprocess management)
- Configuration validation and testing
- Profile management (save/load strategies)
- Import/export configurations
- Credentials management (saves to .env)

Usage:
    python gui_launcher.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import json
import subprocess
import threading
import time
import os
import sys
import webbrowser
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

# Import for version comparison
try:
    from packaging import version
    PACKAGING_AVAILABLE = True
except ImportError:
    PACKAGING_AVAILABLE = False
    print("Warning: packaging library not installed. Update checking will be disabled.")
    print("Install with: pip install packaging")

# Import configuration modules
import config as config_py
from config_loader import config, save_config_to_json, save_env_vars
from config_validator import (
    validate_capital_mode, validate_percentage, validate_positive_number,
    validate_scoring_profile, validate_scoring_weights, validate_spread_thresholds,
    validate_probability_range, validate_hours, validate_log_level,
    validate_api_key, validate_private_key, validate_wallet_address,
    validate_url, validate_telegram_token, validate_telegram_chat_id,
    validate_full_config, validate_credentials
)
from gui_helpers import (
    toggle_field_visibility, toggle_widget_state,
    show_validation_errors, show_validation_warnings,
    validate_and_warn, load_json_file, save_json_file
)
from telegram_notifications import TelegramNotifier

# Disable SSL warnings (Opinion.trade uses self-signed cert)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ToolTip:
    """Tooltip widget for providing help text on hover."""
    
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)
        
    def on_enter(self, event=None):
        """Show tooltip when mouse enters widget."""
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(
            tw, text=self.text, justify='left',
            background="#ffffcc", relief='solid', borderwidth=1,
            font=("TkDefaultFont", 9), padx=5, pady=5
        )
        label.pack()
        
    def on_leave(self, event=None):
        """Hide tooltip when mouse leaves widget."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class BotLauncherGUI:
    """Main GUI application window."""

    # Application version - update this for each release
    VERSION = "1.1.0"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"I Don't Kare about your opinion trading bot - Configuration & Launcher v{self.VERSION}")
        self.root.geometry("1400x900")  # Wider for two-column layout

        # Set window icon if available
        icon_path = Path("icon.ico")
        if icon_path.exists():
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                print(f"Warning: Could not set window icon: {e}")

        # Initialize variables
        self.config_data: Dict[str, Any] = {}
        self.bot_process: Optional[subprocess.Popen] = None
        self.config_changed: bool = False
        self.bot_start_time: float = 0

        # Scoring weights (for custom profile)
        self.scoring_weights = {}

        # Setup GUI components
        self.setup_menu()

        # Create main two-column layout
        main_container = ttk.Frame(self.root)
        main_container.pack(fill='both', expand=True)

        # Left column: Configuration tabs and action buttons
        self.left_column = ttk.Frame(main_container)
        self.left_column.pack(side='left', fill='both', expand=True, padx=(10, 5), pady=10)

        # Right column: Bot launcher and log viewer
        self.right_column = ttk.Frame(main_container)
        self.right_column.pack(side='right', fill='both', expand=True, padx=(5, 10), pady=10)

        # Setup components in columns
        self.setup_tabs()  # Goes into left column
        self.setup_action_buttons()  # Goes into left column
        self.setup_launcher_section()  # Goes into right column
        self.setup_status_bar()  # Goes at bottom of root

        # Check first run and setup files
        self.check_first_run_and_setup()

        # Load initial configuration
        self.load_configuration()

        # Check bot status on startup
        self.check_bot_status()

        # Check for updates (async, non-blocking)
        if PACKAGING_AVAILABLE:
            threading.Thread(target=self.check_for_updates, daemon=True).start()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def setup_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Configuration", command=self.new_configuration)
        file_menu.add_command(label="Load Configuration...", command=self.import_configuration)
        file_menu.add_command(label="Save Configuration", command=self.save_configuration, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.export_configuration)
        file_menu.add_separator()
        file_menu.add_command(label="Import from config.py", command=self.import_from_config_py)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        
        # Profiles menu
        profiles_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Profiles", menu=profiles_menu)
        profiles_menu.add_command(label="Manage Profiles...", command=self.manage_profiles)
        profiles_menu.add_separator()
        profiles_menu.add_command(label="Load Test Mode", command=lambda: self.load_profile("test_mode_profile.json"))
        profiles_menu.add_command(label="Load Aggressive", command=lambda: self.load_profile("aggressive_profile.json"))
        profiles_menu.add_command(label="Load Conservative", command=lambda: self.load_profile("conservative_profile.json"))
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Test Configuration", command=self.test_configuration)
        tools_menu.add_command(label="View Logs", command=self.view_logs)
        tools_menu.add_command(label="Open Bot Folder", command=self.open_folder)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self.show_documentation)
        help_menu.add_command(label="About", command=self.show_about)
        
        # Keyboard shortcuts
        self.root.bind('<Control-s>', lambda e: self.save_configuration())
        
    def setup_tabs(self):
        """Create 6 configuration tabs."""
        self.notebook = ttk.Notebook(self.left_column)
        
        # Tab 1: Capital Management
        self.tab1 = self.create_capital_tab()
        self.notebook.add(self.tab1, text="💰 Capital")
        
        # Tab 2: Market Selection
        self.tab2 = self.create_market_tab()
        self.notebook.add(self.tab2, text="📊 Markets")
        
        # Tab 3: Trading Strategy
        self.tab3 = self.create_trading_tab()
        self.notebook.add(self.tab3, text="💱 Trading")
        
        # Tab 4: Risk Management
        self.tab4 = self.create_risk_tab()
        self.notebook.add(self.tab4, text="🛡️ Risk")
        
        # Tab 5: Monitoring & Alerts
        self.tab5 = self.create_monitoring_tab()
        self.notebook.add(self.tab5, text="🔔 Monitoring")
        
        # Tab 6: Credentials & API
        self.tab6 = self.create_credentials_tab()
        self.notebook.add(self.tab6, text="🔐 Credentials")
        
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Bind tab change to mark config as changed
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: None)
        
    def create_scrollable_frame(self, parent):
        """Create a scrollable frame for tab content."""
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        return scrollable_frame
        
    def create_capital_tab(self) -> ttk.Frame:
        """Create Capital Management tab."""
        frame = ttk.Frame(self.notebook)
        scrollable_frame = self.create_scrollable_frame(frame)
        
        # === Capital Mode Section ===
        mode_frame = ttk.LabelFrame(scrollable_frame, text="Capital Mode", padding=10)
        mode_frame.pack(fill='x', padx=10, pady=5)
        
        self.capital_mode_var = tk.StringVar(value="percentage")
        
        rb_fixed = ttk.Radiobutton(
            mode_frame, 
            text="Fixed Amount", 
            variable=self.capital_mode_var, 
            value="fixed",
            command=self.on_capital_mode_change
        )
        rb_fixed.pack(anchor='w', pady=2)
        ToolTip(rb_fixed, "Use a fixed USDT amount for every position.\nRecommended for testing.\nDefault: Not recommended for production")
        
        rb_percentage = ttk.Radiobutton(
            mode_frame, 
            text="Percentage of Balance", 
            variable=self.capital_mode_var, 
            value="percentage",
            command=self.on_capital_mode_change
        )
        rb_percentage.pack(anchor='w', pady=2)
        ToolTip(rb_percentage, "Use a percentage of current USDT balance.\nRecommended for production.\nDefault: 90% (recommended: 80-95%)")
        
        # === Position Sizing Section ===
        amount_frame = ttk.LabelFrame(scrollable_frame, text="Position Sizing", padding=10)
        amount_frame.pack(fill='x', padx=10, pady=5)
        
        # Fixed Amount
        ttk.Label(amount_frame, text="Fixed Amount (USDT):").grid(row=0, column=0, sticky='w', pady=5)
        self.capital_amount_var = tk.DoubleVar(value=20.0)
        self.capital_amount_entry = ttk.Entry(amount_frame, textvariable=self.capital_amount_var, width=15)
        self.capital_amount_entry.grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(self.capital_amount_entry, "Fixed USDT amount to use per position.\n\nDefault: 20.0\nRange: 10.0 - 10000.0\nExample: 50 = always trade with $50")
        
        # Percentage
        ttk.Label(amount_frame, text="Capital Percentage (%):").grid(row=1, column=0, sticky='w', pady=5)
        self.capital_percentage_var = tk.DoubleVar(value=90.0)
        self.capital_percentage_scale = ttk.Scale(
            amount_frame,
            from_=1, to=100,
            variable=self.capital_percentage_var,
            orient='horizontal',
            length=200
        )
        self.capital_percentage_scale.grid(row=1, column=1, sticky='ew', pady=5, padx=5)

        # Editable entry field
        self.capital_percentage_entry = ttk.Entry(amount_frame, textvariable=self.capital_percentage_var, width=8)
        self.capital_percentage_entry.grid(row=1, column=2, sticky='w', pady=5, padx=5)
        ToolTip(self.capital_percentage_scale, "Percentage of current balance to use per position.\n\nDefault: 90%\nRecommended: 80-95%\nExample: 90 = use 90% of balance")
        ToolTip(self.capital_percentage_entry, "Percentage of current balance to use per position.\n\nDefault: 90%\nRecommended: 80-95%\nExample: 90 = use 90% of balance")
        
        # Auto Reinvest
        self.auto_reinvest_var = tk.BooleanVar(value=True)
        cb_reinvest = ttk.Checkbutton(
            amount_frame, 
            text="Auto Reinvest (search for next market after closing)",
            variable=self.auto_reinvest_var
        )
        cb_reinvest.grid(row=2, column=0, columnspan=3, sticky='w', pady=5)
        ToolTip(cb_reinvest, "Automatically search for next market after closing position.\n\nDefault: True (enabled)\nUncheck to stop after one trading cycle")
        
        # === Safety Limits Section ===
        safety_frame = ttk.LabelFrame(scrollable_frame, text="Safety Limits", padding=10)
        safety_frame.pack(fill='x', padx=10, pady=5)
        
        # Min Balance
        ttk.Label(safety_frame, text="Min Balance to Continue (USDT):").grid(row=0, column=0, sticky='w', pady=5)
        self.min_balance_var = tk.DoubleVar(value=60.0)
        ttk.Entry(safety_frame, textvariable=self.min_balance_var, width=15).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(safety_frame.winfo_children()[-1], "Stop trading if balance falls below this.\n\nDefault: 60.0 USDT\nRecommended: > min_position_size\nPrevents trading with insufficient capital")
        
        # Min Position Size
        ttk.Label(safety_frame, text="Min Position Size (USDT):").grid(row=1, column=0, sticky='w', pady=5)
        self.min_position_var = tk.DoubleVar(value=50.0)
        ttk.Entry(safety_frame, textvariable=self.min_position_var, width=15).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(safety_frame.winfo_children()[-1], "Minimum position size for qualifying trades.\n\nDefault: 50.0 USDT\nNote: 50 USDT = qualifies for airdrop points\nLower = more opportunities, but may miss rewards")
        
        # Dust Threshold
        ttk.Label(safety_frame, text="Dust Threshold (USDT):").grid(row=2, column=0, sticky='w', pady=5)
        self.dust_threshold_var = tk.DoubleVar(value=30.0)
        ttk.Entry(safety_frame, textvariable=self.dust_threshold_var, width=15).grid(row=2, column=1, sticky='w', pady=5, padx=5)
        ToolTip(safety_frame.winfo_children()[-1], "Ignore positions smaller than this.\n\nDefault: 30.0 USDT\nRecommended (moderately safe minimum):\n- Fixed mode: 5% of planned position\n- Minimum: 5 USDT\n\nLower values allow smaller trades but may be unprofitable due to gas fees.\nValidation warning shown if below recommended values.")
        
        return frame
        
    def update_percentage_label(self, value=None):
        """Update percentage label when scale changes."""
        self.capital_percentage_label.config(text=f"{self.capital_percentage_var.get():.0f}%")
        
    def on_capital_mode_change(self):
        """Enable/disable fields based on capital mode."""
        mode = self.capital_mode_var.get()
        if mode == 'fixed':
            self.capital_amount_entry.config(state='normal')
            self.capital_percentage_scale.config(state='disabled')
        else:
            self.capital_amount_entry.config(state='disabled')
            self.capital_percentage_scale.config(state='normal')
        
    def create_market_tab(self) -> ttk.Frame:
        """Create Market Selection tab."""
        frame = ttk.Frame(self.notebook)
        scrollable_frame = self.create_scrollable_frame(frame)
        
        # === Scoring Profile Section ===
        profile_frame = ttk.LabelFrame(scrollable_frame, text="Scoring Profile", padding=10)
        profile_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(profile_frame, text="Profile:").grid(row=0, column=0, sticky='w', pady=5)
        
        self.scoring_profile_var = tk.StringVar(value="production_farming")
        self.scoring_profile_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.scoring_profile_var,
            values=["production_farming", "test_quick_fill", "balanced", "liquidity_farming", "custom"],
            state='readonly',
            width=20
        )
        self.scoring_profile_combo.grid(row=0, column=1, sticky='w', pady=5, padx=5)
        self.scoring_profile_combo.bind('<<ComboboxSelected>>', self.on_scoring_profile_change)
        ToolTip(self.scoring_profile_combo, "Scoring algorithm for market selection.\n\nproduction_farming: Balanced approach (default)\ntest_quick_fill: Prioritize fast fills\nbalanced: Equal weights\nliquidity_farming: High volume markets\ncustom: Edit weights manually")
        
        # === Scoring Weights Section ===
        weights_frame = ttk.LabelFrame(scrollable_frame, text="Scoring Weights (custom profile only)", padding=10)
        weights_frame.pack(fill='x', padx=10, pady=5)
        
        # Weight fields
        self.weight_vars = {}
        weight_names = [
            ('price_balance', 'Price Balance', 0.45),
            ('hourglass_advanced', 'Hourglass Shape', 0.25),
            ('spread', 'Spread', 0.20),
            ('volume_24h', '24h Volume', 0.10),
            ('bias_score', 'Bias Score', 0.0),
            ('liquidity_depth', 'Liquidity Depth', 0.0),
        ]
        
        for i, (key, label, default) in enumerate(weight_names):
            ttk.Label(weights_frame, text=f"{label}:").grid(row=i, column=0, sticky='w', pady=2)
            
            var = tk.DoubleVar(value=default)
            entry = ttk.Entry(weights_frame, textvariable=var, width=10, state='disabled')
            entry.grid(row=i, column=1, sticky='w', pady=2, padx=5)
            
            self.weight_vars[key] = (var, entry)
            
            # Validation on change
            var.trace_add('write', self.validate_weights_sum)
        
        # Sum display
        ttk.Label(weights_frame, text="Total:").grid(row=len(weight_names), column=0, sticky='w', pady=5)
        self.weights_sum_label = ttk.Label(weights_frame, text="1.00", foreground="green")
        self.weights_sum_label.grid(row=len(weight_names), column=1, sticky='w', pady=5)
        
        # === Market Filters Section ===
        filters_frame = ttk.LabelFrame(scrollable_frame, text="Market Filters", padding=10)
        filters_frame.pack(fill='x', padx=10, pady=5)
        
        # Bonus Markets
        ttk.Label(filters_frame, text="Bonus Markets File:").grid(row=0, column=0, sticky='w', pady=5)
        self.bonus_file_var = tk.StringVar(value="")
        bonus_entry = ttk.Entry(filters_frame, textvariable=self.bonus_file_var, width=30)
        bonus_entry.grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ttk.Button(filters_frame, text="Browse...", command=self.browse_bonus_file).grid(row=0, column=2, pady=5)
        ToolTip(bonus_entry, "Optional: File with bonus market addresses.\nThese markets get priority scoring.\nDefault: None (no bonus markets)")
        
        # Bonus Multiplier
        ttk.Label(filters_frame, text="Bonus Multiplier:").grid(row=1, column=0, sticky='w', pady=5)
        self.bonus_multiplier_var = tk.DoubleVar(value=1.0)
        ttk.Entry(filters_frame, textvariable=self.bonus_multiplier_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(filters_frame.winfo_children()[-1], "Score multiplier for bonus markets.\n\nDefault: 1.0 (no bonus)\nExample: 1.5 = 50% higher score")
        
        # Min Orderbook Orders
        ttk.Label(filters_frame, text="Min Orderbook Orders:").grid(row=2, column=0, sticky='w', pady=5)
        self.min_orderbook_var = tk.IntVar(value=1)
        ttk.Spinbox(filters_frame, from_=1, to=20, textvariable=self.min_orderbook_var, width=10).grid(row=2, column=1, sticky='w', pady=5, padx=5)
        ToolTip(filters_frame.winfo_children()[-1], "Minimum number of orders in orderbook.\n\nDefault: 1\nHigher = more liquid markets only")
        
        # === Probability Range Section ===
        prob_frame = ttk.LabelFrame(scrollable_frame, text="Outcome Probability Range", padding=10)
        prob_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(prob_frame, text="Min Probability:").grid(row=0, column=0, sticky='w', pady=5)
        self.outcome_min_prob_var = tk.DoubleVar(value=0.20)
        ttk.Entry(prob_frame, textvariable=self.outcome_min_prob_var, width=10).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(prob_frame.winfo_children()[-1], "Minimum outcome probability to consider.\n\nDefault: 0.20 (20%)\nRange: 0.0 - 1.0")
        
        ttk.Label(prob_frame, text="Max Probability:").grid(row=1, column=0, sticky='w', pady=5)
        self.outcome_max_prob_var = tk.DoubleVar(value=0.90)
        ttk.Entry(prob_frame, textvariable=self.outcome_max_prob_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(prob_frame.winfo_children()[-1], "Maximum outcome probability to consider.\n\nDefault: 0.90 (90%)\nRange: 0.0 - 1.0")
        
        # === Time Range Section ===
        time_frame = ttk.LabelFrame(scrollable_frame, text="Time Until Market Close", padding=10)
        time_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(time_frame, text="Min Hours:").grid(row=0, column=0, sticky='w', pady=5)
        self.min_hours_var = tk.StringVar(value="")
        ttk.Entry(time_frame, textvariable=self.min_hours_var, width=10).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(time_frame.winfo_children()[-1], "Minimum hours until market close.\n\nDefault: None (no minimum)\nExample: 24 = only markets closing in >24h")
        
        ttk.Label(time_frame, text="Max Hours:").grid(row=1, column=0, sticky='w', pady=5)
        self.max_hours_var = tk.StringVar(value="168")
        ttk.Entry(time_frame, textvariable=self.max_hours_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(time_frame.winfo_children()[-1], "Maximum hours until market close.\n\nDefault: 168 (7 days)\nExample: 72 = only markets closing in <72h")
        
        return frame
        
    def on_scoring_profile_change(self, event=None):
        """Handle scoring profile selection change."""
        profile = self.scoring_profile_var.get()
        
        if profile == 'custom':
            # Enable all weight fields for editing
            for var, entry in self.weight_vars.values():
                entry.config(state='normal')
        else:
            # Load preset weights and disable fields
            preset_weights = self.get_preset_weights(profile)
            
            for key, (var, entry) in self.weight_vars.items():
                var.set(preset_weights.get(key, 0.0))
                entry.config(state='disabled')
        
        self.validate_weights_sum()
        
    def get_preset_weights(self, profile: str) -> dict:
        """Get preset weights for a scoring profile."""
        presets = {
            'production_farming': {
                'price_balance': 0.45,
                'hourglass_advanced': 0.25,
                'spread': 0.20,
                'volume_24h': 0.10,
                'bias_score': 0.0,
                'liquidity_depth': 0.0,
            },
            'test_quick_fill': {
                'price_balance': 0.0,
                'hourglass_advanced': 0.0,
                'spread': 1.0,
                'volume_24h': 0.0,
                'bias_score': 0.0,
                'liquidity_depth': 0.0,
            },
            'balanced': {
                'price_balance': 0.25,
                'hourglass_advanced': 0.0,
                'spread': 0.25,
                'volume_24h': 0.25,
                'bias_score': 0.0,
                'liquidity_depth': 0.25,
            },
            'liquidity_farming': {
                'price_balance': 0.0,
                'hourglass_advanced': 0.0,
                'spread': 0.15,
                'volume_24h': 0.35,
                'bias_score': 0.50,
                'liquidity_depth': 0.0,
            },
        }
        
        return presets.get(profile, {})
        
    def validate_weights_sum(self, *args):
        """Validate that weights sum to ~1.0."""
        total = sum(var.get() for var, _ in self.weight_vars.values())
        
        self.weights_sum_label.config(text=f"{total:.2f}")
        
        if abs(total - 1.0) < 0.01:
            self.weights_sum_label.config(foreground="green")
        elif abs(total - 1.0) < 0.1:
            self.weights_sum_label.config(foreground="orange")
        else:
            self.weights_sum_label.config(foreground="red")
            
    def browse_bonus_file(self):
        """Browse for bonus markets file."""
        filename = filedialog.askopenfilename(
            title="Select Bonus Markets File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.bonus_file_var.set(filename)
        
    def create_trading_tab(self) -> ttk.Frame:
        """Create Trading Strategy tab."""
        frame = ttk.Frame(self.notebook)
        scrollable_frame = self.create_scrollable_frame(frame)
        
        # === Spread Thresholds Section ===
        spread_frame = ttk.LabelFrame(scrollable_frame, text="Spread Thresholds", padding=10)
        spread_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(spread_frame, text="Spread defines market categories for pricing strategy.").grid(row=0, column=0, columnspan=3, sticky='w', pady=5)
        
        ttk.Label(spread_frame, text="Threshold 1 (TINY):").grid(row=1, column=0, sticky='w', pady=5)
        self.spread_threshold_1_var = tk.DoubleVar(value=0.20)
        ttk.Entry(spread_frame, textvariable=self.spread_threshold_1_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ttk.Label(spread_frame, text="<= 0.20 = TINY spread").grid(row=1, column=2, sticky='w', pady=5)
        
        ttk.Label(spread_frame, text="Threshold 2 (SMALL):").grid(row=2, column=0, sticky='w', pady=5)
        self.spread_threshold_2_var = tk.DoubleVar(value=0.50)
        ttk.Entry(spread_frame, textvariable=self.spread_threshold_2_var, width=10).grid(row=2, column=1, sticky='w', pady=5, padx=5)
        ttk.Label(spread_frame, text="<= 0.50 = SMALL spread").grid(row=2, column=2, sticky='w', pady=5)
        
        ttk.Label(spread_frame, text="Threshold 3 (MEDIUM):").grid(row=3, column=0, sticky='w', pady=5)
        self.spread_threshold_3_var = tk.DoubleVar(value=1.00)
        ttk.Entry(spread_frame, textvariable=self.spread_threshold_3_var, width=10).grid(row=3, column=1, sticky='w', pady=5, padx=5)
        ttk.Label(spread_frame, text="<= 1.00 = MEDIUM, >1.00 = WIDE").grid(row=3, column=2, sticky='w', pady=5)
        
        # === Improvement Amounts Section ===
        improvement_frame = ttk.LabelFrame(scrollable_frame, text="Price Improvement (how much to improve best price)", padding=10)
        improvement_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(improvement_frame, text="Improvement TINY:").grid(row=0, column=0, sticky='w', pady=5)
        self.improvement_tiny_var = tk.DoubleVar(value=0.00)
        ttk.Entry(improvement_frame, textvariable=self.improvement_tiny_var, width=10).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(improvement_frame.winfo_children()[-1], "Price improvement for TINY spread markets.\n\nDefault: 0.00 (match best price)\nExample: 0.05 = improve by $0.05")
        
        ttk.Label(improvement_frame, text="Improvement SMALL:").grid(row=1, column=0, sticky='w', pady=5)
        self.improvement_small_var = tk.DoubleVar(value=0.10)
        ttk.Entry(improvement_frame, textvariable=self.improvement_small_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(improvement_frame.winfo_children()[-1], "Price improvement for SMALL spread markets.\n\nDefault: 0.10\nExample: 0.10 = improve by $0.10")
        
        ttk.Label(improvement_frame, text="Improvement MEDIUM:").grid(row=2, column=0, sticky='w', pady=5)
        self.improvement_medium_var = tk.DoubleVar(value=0.20)
        ttk.Entry(improvement_frame, textvariable=self.improvement_medium_var, width=10).grid(row=2, column=1, sticky='w', pady=5, padx=5)
        ToolTip(improvement_frame.winfo_children()[-1], "Price improvement for MEDIUM spread markets.\n\nDefault: 0.20\nExample: 0.20 = improve by $0.20")
        
        ttk.Label(improvement_frame, text="Improvement WIDE:").grid(row=3, column=0, sticky='w', pady=5)
        self.improvement_wide_var = tk.DoubleVar(value=0.30)
        ttk.Entry(improvement_frame, textvariable=self.improvement_wide_var, width=10).grid(row=3, column=1, sticky='w', pady=5, padx=5)
        ToolTip(improvement_frame.winfo_children()[-1], "Price improvement for WIDE spread markets.\n\nDefault: 0.30\nExample: 0.30 = improve by $0.30")
        
        # === Precision Section ===
        precision_frame = ttk.LabelFrame(scrollable_frame, text="Precision & Safety (Advanced)", padding=10)
        precision_frame.pack(fill='x', padx=10, pady=5)

        # Lock checkbox
        self.enable_precision_edit_var = tk.BooleanVar(value=False)
        cb_precision = ttk.Checkbutton(
            precision_frame,
            text="⚠️ Enable editing (Advanced users only)",
            variable=self.enable_precision_edit_var,
            command=self.on_precision_toggle
        )
        cb_precision.grid(row=0, column=0, columnspan=3, sticky='w', pady=5)
        ToolTip(cb_precision, "⚠️ WARNING: Don't change these values unless you know what you're doing!\n\nThese settings control critical calculation precision.\nIncorrect values can cause rounding errors or trading failures.")

        ttk.Label(precision_frame, text="Safety Margin (cents):").grid(row=1, column=0, sticky='w', pady=5)
        self.safety_margin_var = tk.DoubleVar(value=0.001)
        self.safety_margin_entry = ttk.Entry(precision_frame, textvariable=self.safety_margin_var, width=10, state='disabled')
        self.safety_margin_entry.grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(self.safety_margin_entry, "Safety margin for price calculations.\n\nDefault: 0.001 ($0.001)\nPrevents rounding errors")

        ttk.Label(precision_frame, text="Price Decimals:").grid(row=2, column=0, sticky='w', pady=5)
        self.price_decimals_var = tk.IntVar(value=3)
        self.price_decimals_spinbox = ttk.Spinbox(precision_frame, from_=1, to=6, textvariable=self.price_decimals_var, width=10, state='disabled')
        self.price_decimals_spinbox.grid(row=2, column=1, sticky='w', pady=5, padx=5)
        ToolTip(self.price_decimals_spinbox, "Decimal places for prices.\n\nDefault: 3\nExample: 3 = $0.500")

        ttk.Label(precision_frame, text="Amount Decimals:").grid(row=3, column=0, sticky='w', pady=5)
        self.amount_decimals_var = tk.IntVar(value=2)
        self.amount_decimals_spinbox = ttk.Spinbox(precision_frame, from_=0, to=6, textvariable=self.amount_decimals_var, width=10, state='disabled')
        self.amount_decimals_spinbox.grid(row=3, column=1, sticky='w', pady=5, padx=5)
        ToolTip(self.amount_decimals_spinbox, "Decimal places for amounts.\n\nDefault: 2\nExample: 2 = 100.25 shares")
        
        return frame
        
    def create_risk_tab(self) -> ttk.Frame:
        """Create Risk Management tab."""
        frame = ttk.Frame(self.notebook)
        scrollable_frame = self.create_scrollable_frame(frame)
        
        # === Stop-Loss Section ===
        stoploss_frame = ttk.LabelFrame(scrollable_frame, text="Stop-Loss Protection", padding=10)
        stoploss_frame.pack(fill='x', padx=10, pady=5)
        
        self.enable_stop_loss_var = tk.BooleanVar(value=True)
        cb_stoploss = ttk.Checkbutton(
            stoploss_frame,
            text="Enable Stop-Loss",
            variable=self.enable_stop_loss_var,
            command=self.on_stop_loss_toggle
        )
        cb_stoploss.pack(anchor='w', pady=5)
        ToolTip(cb_stoploss, "Enable automatic stop-loss when position loses value.\n\nDefault: Enabled (recommended)\nDisable only for testing")
        
        # Stop-Loss Trigger with slider and label on right
        sl_container = ttk.Frame(stoploss_frame)
        sl_container.pack(fill='x', pady=5)

        ttk.Label(sl_container, text="Stop-Loss Trigger (%):").pack(side='left', padx=(0, 10))

        self.stop_loss_trigger_var = tk.DoubleVar(value=-10.0)
        self.stop_loss_scale = ttk.Scale(
            sl_container,
            from_=-50, to=0,
            variable=self.stop_loss_trigger_var,
            orient='horizontal',
            length=250
        )
        self.stop_loss_scale.pack(side='left', fill='x', expand=True)

        # Editable entry field
        self.stop_loss_entry = ttk.Entry(sl_container, textvariable=self.stop_loss_trigger_var, width=8)
        self.stop_loss_entry.pack(side='left', padx=(10, 0))
        ToolTip(self.stop_loss_scale, "Trigger stop-loss when position loses this %.\n\nDefault: -10%\nExample: -10 = sell if position down 10%\nRecommended: -5% to -15%")
        ToolTip(self.stop_loss_entry, "Trigger stop-loss when position loses this %.\n\nDefault: -10%\nExample: -10 = sell if position down 10%\nRecommended: -5% to -15%")
        
        ttk.Label(stoploss_frame, text="Stop-Loss Aggressive Offset:").pack(anchor='w', pady=5)
        self.stop_loss_offset_var = tk.DoubleVar(value=0.001)
        ttk.Entry(stoploss_frame, textvariable=self.stop_loss_offset_var, width=10).pack(anchor='w', pady=5)
        ToolTip(stoploss_frame.winfo_children()[-1], "Price offset for aggressive stop-loss exit.\n\nDefault: 0.001\nEnsures quick exit in emergency")
        
        # === Liquidity Protection Section ===
        liquidity_frame = ttk.LabelFrame(scrollable_frame, text="Liquidity Protection", padding=10)
        liquidity_frame.pack(fill='x', padx=10, pady=5)
        
        self.liquidity_auto_cancel_var = tk.BooleanVar(value=True)
        cb_liquidity = ttk.Checkbutton(
            liquidity_frame,
            text="Enable Liquidity Auto-Cancel",
            variable=self.liquidity_auto_cancel_var
        )
        cb_liquidity.pack(anchor='w', pady=5)
        ToolTip(cb_liquidity, "Cancel orders if liquidity drops significantly.\n\nDefault: Enabled\nProtects against illiquid markets")
        
        # Bid Drop Threshold with slider and editable entry on right
        bid_container = ttk.Frame(liquidity_frame)
        bid_container.pack(fill='x', pady=5)

        ttk.Label(bid_container, text="Bid Drop Threshold (%):").pack(side='left', padx=(0, 10))

        self.liquidity_bid_drop_var = tk.DoubleVar(value=25.0)
        bid_scale = ttk.Scale(
            bid_container,
            from_=0, to=100,
            variable=self.liquidity_bid_drop_var,
            orient='horizontal',
            length=250
        )
        bid_scale.pack(side='left', fill='x', expand=True)

        # Editable entry field
        liq_bid_entry = ttk.Entry(bid_container, textvariable=self.liquidity_bid_drop_var, width=8)
        liq_bid_entry.pack(side='left', padx=(10, 0))
        ToolTip(bid_scale, "Cancel if bid liquidity drops by this %.\n\nDefault: 25%\nHigher = more tolerant of liquidity changes")
        ToolTip(liq_bid_entry, "Cancel if bid liquidity drops by this %.\n\nDefault: 25%\nHigher = more tolerant of liquidity changes")
        
        # Spread Threshold with slider and editable entry on right
        spread_container = ttk.Frame(liquidity_frame)
        spread_container.pack(fill='x', pady=5)

        ttk.Label(spread_container, text="Spread Threshold (%):").pack(side='left', padx=(0, 10))

        self.liquidity_spread_var = tk.DoubleVar(value=15.0)
        spread_scale = ttk.Scale(
            spread_container,
            from_=0, to=100,
            variable=self.liquidity_spread_var,
            orient='horizontal',
            length=250
        )
        spread_scale.pack(side='left', fill='x', expand=True)

        # Editable entry field
        liq_spread_entry = ttk.Entry(spread_container, textvariable=self.liquidity_spread_var, width=8)
        liq_spread_entry.pack(side='left', padx=(10, 0))
        ToolTip(spread_scale, "Cancel if spread increases by this %.\n\nDefault: 15%\nHigher = more tolerant of spread widening")
        ToolTip(liq_spread_entry, "Cancel if spread increases by this %.\n\nDefault: 15%\nHigher = more tolerant of spread widening")
        
        # === Order Timeouts Section ===
        timeout_frame = ttk.LabelFrame(scrollable_frame, text="Order Timeouts", padding=10)
        timeout_frame.pack(fill='x', padx=10, pady=5)

        ttk.Label(timeout_frame, text="Buy Order Timeout (hours):").grid(row=0, column=0, sticky='w', pady=5)
        self.buy_timeout_var = tk.DoubleVar(value=8.0)
        ttk.Entry(timeout_frame, textvariable=self.buy_timeout_var, width=10).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(timeout_frame.winfo_children()[-1], "Cancel buy order if not filled within this time.\n\nDefault: 8 hours\nShorter = faster capital rotation")

        ttk.Label(timeout_frame, text="Sell Order Timeout (hours):").grid(row=1, column=0, sticky='w', pady=5)
        self.sell_timeout_var = tk.DoubleVar(value=8.0)
        ttk.Entry(timeout_frame, textvariable=self.sell_timeout_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(timeout_frame.winfo_children()[-1], "Cancel sell order if not filled within this time.\n\nDefault: 8 hours\nLonger = more patient exits")

        # === Sell Order Repricing Section ===
        repricing_frame = ttk.LabelFrame(scrollable_frame, text="Sell Order Repricing Control", padding=10)
        repricing_frame.pack(fill='x', padx=10, pady=5)

        self.enable_sell_repricing_var = tk.BooleanVar(value=True)
        cb_repricing = ttk.Checkbutton(
            repricing_frame,
            text="Enable Automatic Sell Order Repricing",
            variable=self.enable_sell_repricing_var,
            command=self.on_sell_repricing_toggle
        )
        cb_repricing.pack(anchor='w', pady=5)
        ToolTip(cb_repricing,
            "Enable automatic repricing of sell orders when orderbook moves.\n\n"
            "Enabled: Aggressively compete for best price (good for point farming)\n"
            "Disabled: Maintain original sell price (good for profit maximization)\n\n"
            "Default: Enabled")

        # Liquidity Threshold
        liq_threshold_container = ttk.Frame(repricing_frame)
        liq_threshold_container.pack(fill='x', pady=5)

        ttk.Label(liq_threshold_container, text="Liquidity Trigger Threshold (%):").pack(side='left', padx=(0, 10))

        self.sell_reprice_threshold_var = tk.DoubleVar(value=50.0)

        # Scale for visual adjustment
        self.sell_reprice_threshold_scale = ttk.Scale(
            liq_threshold_container,
            from_=1, to=1000,
            variable=self.sell_reprice_threshold_var,
            orient='horizontal',
            length=200
        )
        self.sell_reprice_threshold_scale.pack(side='left', fill='x', expand=True, padx=5)

        # Entry field for direct input (on the right)
        self.sell_reprice_threshold_entry = ttk.Entry(
            liq_threshold_container,
            textvariable=self.sell_reprice_threshold_var,
            width=10
        )
        self.sell_reprice_threshold_entry.pack(side='left', padx=(10, 0))

        tooltip_text = (
            "Reprice when total shares at better prices reach this % of our order size.\n\n"
            "Example: 50% with 100 share sell order = reprice when ≥50 shares appear at better prices\n\n"
            "Lower = more aggressive repricing\n"
            "Higher = more conservative repricing\n\n"
            "Default: 50%\n"
            "Recommended: 50-250%"
        )
        ToolTip(self.sell_reprice_threshold_entry, tooltip_text)
        ToolTip(self.sell_reprice_threshold_scale, tooltip_text)

        # Allow Below Buy Price
        self.allow_below_buy_var = tk.BooleanVar(value=False)
        self.cb_allow_below = ttk.Checkbutton(
            repricing_frame,
            text="Allow Repricing Below Buy Price",
            variable=self.allow_below_buy_var,
            command=self.on_allow_below_buy_toggle
        )
        self.cb_allow_below.pack(anchor='w', pady=5)
        ToolTip(self.cb_allow_below,
            "Allow sell price to go below buy price (selling at loss).\n\n"
            "Enabled: Can sell at loss if needed (for point farming)\n"
            "Disabled: Never go below buy price (for profit protection)\n\n"
            "Default: Disabled (recommended for profit trading)")

        # Max Price Reduction (only active when allow_below_buy is enabled)
        max_reduction_container = ttk.Frame(repricing_frame)
        max_reduction_container.pack(fill='x', pady=5)

        ttk.Label(max_reduction_container, text="Max Price Reduction vs Buy Price (%):").pack(side='left', padx=(0, 10))

        self.max_sell_reduction_var = tk.DoubleVar(value=5.0)
        self.max_sell_reduction_entry = ttk.Entry(max_reduction_container, textvariable=self.max_sell_reduction_var, width=8)
        self.max_sell_reduction_entry.pack(side='left', padx=5)
        ToolTip(self.max_sell_reduction_entry,
            "Maximum allowed price reduction relative to buy price.\n\n"
            "Example: 5% means sell price can go down to buy_price * 0.95\n\n"
            "Must be >= stop-loss percentage for safety\n"
            "Only active when 'Allow Below Buy Price' is enabled\n\n"
            "Default: 5%")

        # Repricing Scale Mode
        mode_container = ttk.Frame(repricing_frame)
        mode_container.pack(fill='x', pady=5)

        ttk.Label(mode_container, text="Repricing Scale Mode:").pack(side='left', padx=(0, 10))

        self.reprice_scale_mode_var = tk.StringVar(value="best")
        mode_combo = ttk.Combobox(
            mode_container,
            textvariable=self.reprice_scale_mode_var,
            values=["best", "second_best", "liquidity_percent"],
            state='readonly',
            width=18
        )
        mode_combo.pack(side='left', padx=5)
        mode_combo.bind('<<ComboboxSelected>>', lambda e: self.on_reprice_mode_change())
        ToolTip(mode_combo,
            "How aggressively to reprice when threshold is met:\n\n"
            "best: Match the best (lowest) competing ask price\n"
            "second_best: Match the second-best ask price\n"
            "liquidity_percent: Target price level based on liquidity %\n\n"
            "Default: best (most aggressive)")

        # Liquidity Target % (only for liquidity_percent mode)
        liq_target_container = ttk.Frame(repricing_frame)
        liq_target_container.pack(fill='x', pady=5)

        ttk.Label(liq_target_container, text="Liquidity Target (%):").pack(side='left', padx=(0, 10))

        self.liq_target_var = tk.DoubleVar(value=30.0)

        # Scale for visual adjustment
        self.liq_target_scale = ttk.Scale(
            liq_target_container,
            from_=1, to=100,
            variable=self.liq_target_var,
            orient='horizontal',
            length=200
        )
        self.liq_target_scale.pack(side='left', fill='x', expand=True, padx=5)

        # Entry field for direct input (on the right)
        self.liq_target_entry = ttk.Entry(
            liq_target_container,
            textvariable=self.liq_target_var,
            width=10
        )
        self.liq_target_entry.pack(side='left', padx=(10, 0))

        tooltip_text = (
            "Target price level that captures this % of better liquidity.\n\n"
            "Example: 30% means reprice to level where cumulative better orders = 30% of total\n\n"
            "Only used when mode = 'liquidity_percent'\n\n"
            "Default: 30%\n"
            "Range: 1-100%"
        )
        ToolTip(self.liq_target_entry, tooltip_text)
        ToolTip(self.liq_target_scale, tooltip_text)

        # Liquidity Return % (only for liquidity_percent mode)
        liq_return_container = ttk.Frame(repricing_frame)
        liq_return_container.pack(fill='x', pady=5)

        ttk.Label(liq_return_container, text="Liquidity Return Threshold (%):").pack(side='left', padx=(0, 10))

        self.liq_return_var = tk.DoubleVar(value=20.0)

        # Scale for visual adjustment
        self.liq_return_scale = ttk.Scale(
            liq_return_container,
            from_=1, to=100,
            variable=self.liq_return_var,
            orient='horizontal',
            length=200
        )
        self.liq_return_scale.pack(side='left', fill='x', expand=True, padx=5)

        # Entry field for direct input (on the right)
        self.liq_return_entry = ttk.Entry(
            liq_return_container,
            textvariable=self.liq_return_var,
            width=10
        )
        self.liq_return_entry.pack(side='left', padx=(10, 0))

        tooltip_text = (
            "Return to higher price when better liquidity drops below this %.\n\n"
            "Example: If target=30% and return=20%, move down at 30% but move up when it drops to 20%\n\n"
            "Must be < Liquidity Target %\n"
            "Only used when mode = 'liquidity_percent'\n\n"
            "Default: 20%\n"
            "Range: 1-100%"
        )
        ToolTip(self.liq_return_entry, tooltip_text)
        ToolTip(self.liq_return_scale, tooltip_text)

        # Dynamic Price Adjustment
        self.enable_dynamic_adjustment_var = tk.BooleanVar(value=True)
        self.cb_dynamic_adjustment = ttk.Checkbutton(
            repricing_frame,
            text="Enable Dynamic Price Adjustment",
            variable=self.enable_dynamic_adjustment_var
        )
        self.cb_dynamic_adjustment.pack(anchor='w', pady=5)
        ToolTip(self.cb_dynamic_adjustment,
            "Automatically increase price when market conditions improve.\n\n"
            "Enabled: Dynamically adjust price up/down based on orderbook\n"
            "Disabled: Only decrease price, never increase\n\n"
            "Only applies to 'second_best' and 'liquidity_percent' modes\n\n"
            "Default: Enabled")

        # Initialize widget states
        self.on_reprice_mode_change()
        self.on_sell_repricing_toggle()
        self.on_allow_below_buy_toggle()

        return frame
        
    def update_stop_loss_label(self, value=None):
        """Update stop-loss label."""
        self.stop_loss_label.config(text=f"{self.stop_loss_trigger_var.get():.1f}%")
        
    def on_stop_loss_toggle(self):
        """Handle stop-loss toggle."""
        toggle_widget_state(self.enable_stop_loss_var, self.stop_loss_scale)

    def on_precision_toggle(self):
        """Handle precision settings toggle."""
        state = 'normal' if self.enable_precision_edit_var.get() else 'disabled'
        if hasattr(self, 'safety_margin_entry'):
            self.safety_margin_entry.config(state=state)
        if hasattr(self, 'price_decimals_spinbox'):
            self.price_decimals_spinbox.config(state=state)
        if hasattr(self, 'amount_decimals_spinbox'):
            self.amount_decimals_spinbox.config(state=state)

    def on_sell_repricing_toggle(self):
        """Handle sell repricing toggle - enable/disable all repricing parameters."""
        enabled = self.enable_sell_repricing_var.get()
        state = 'normal' if enabled else 'disabled'

        # Toggle main repricing controls
        self.sell_reprice_threshold_entry.config(state=state)
        self.sell_reprice_threshold_scale.config(state=state)
        self.cb_allow_below.config(state=state)

        # Call other toggles to update their dependent widgets
        self.on_allow_below_buy_toggle()
        self.on_reprice_mode_change()

    def on_allow_below_buy_toggle(self):
        """Handle allow below buy price toggle."""
        # Only enable max reduction entry if both repricing AND allow_below are enabled
        enabled = self.enable_sell_repricing_var.get() and self.allow_below_buy_var.get()
        self.max_sell_reduction_entry.config(state='normal' if enabled else 'disabled')

    def on_reprice_mode_change(self):
        """Handle repricing mode change - show/hide mode-specific controls."""
        mode = self.reprice_scale_mode_var.get()
        repricing_enabled = self.enable_sell_repricing_var.get()

        # Liquidity target/return are only for 'liquidity_percent' mode
        liq_controls_enabled = (mode == 'liquidity_percent' and repricing_enabled)

        self.liq_target_entry.config(state='normal' if liq_controls_enabled else 'disabled')
        self.liq_target_scale.config(state='normal' if liq_controls_enabled else 'disabled')
        self.liq_return_entry.config(state='normal' if liq_controls_enabled else 'disabled')
        self.liq_return_scale.config(state='normal' if liq_controls_enabled else 'disabled')

        # Dynamic adjustment is only for 'second_best' and 'liquidity_percent' modes
        dynamic_enabled = (mode in ['second_best', 'liquidity_percent'] and repricing_enabled)
        self.cb_dynamic_adjustment.config(state='normal' if dynamic_enabled else 'disabled')

    def create_monitoring_tab(self) -> ttk.Frame:
        """Create Monitoring & Alerts tab."""
        frame = ttk.Frame(self.notebook)
        scrollable_frame = self.create_scrollable_frame(frame)
        
        # === Logging Section ===
        logging_frame = ttk.LabelFrame(scrollable_frame, text="Logging", padding=10)
        logging_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(logging_frame, text="Log Level:").grid(row=0, column=0, sticky='w', pady=5)
        self.log_level_var = tk.StringVar(value="INFO")
        ttk.Combobox(
            logging_frame,
            textvariable=self.log_level_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            state='readonly',
            width=15
        ).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(logging_frame.winfo_children()[-1], "Logging verbosity level.\n\nDEBUG: Very detailed (for troubleshooting)\nINFO: Standard operation (recommended)\nWARNING: Only warnings and errors\nERROR: Only errors\nCRITICAL: Only critical failures")
        
        ttk.Label(logging_frame, text="Log File:").grid(row=1, column=0, sticky='w', pady=5)
        self.log_file_var = tk.StringVar(value="logs/idk_bot.log")
        ttk.Entry(logging_frame, textvariable=self.log_file_var, width=30).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ttk.Button(logging_frame, text="Browse...", command=self.browse_log_file).grid(row=1, column=2, pady=5)
        ToolTip(logging_frame.winfo_children()[-2], "Path to log file.\n\nDefault: logs/idk_bot.log\nLogs rotate daily: idk_bot_YYYYMMDD.log\nAll bot activity is logged here")
        
        # === Alerts Section ===
        alerts_frame = ttk.LabelFrame(scrollable_frame, text="Alert Notifications", padding=10)
        alerts_frame.pack(fill='x', padx=10, pady=5)

        self.alert_order_filled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(alerts_frame, text="Alert on Order Filled", variable=self.alert_order_filled_var).pack(anchor='w', pady=2)

        self.alert_position_closed_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(alerts_frame, text="Alert on Position Closed", variable=self.alert_position_closed_var).pack(anchor='w', pady=2)

        self.alert_error_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(alerts_frame, text="Alert on Error", variable=self.alert_error_var).pack(anchor='w', pady=2)

        self.alert_insufficient_balance_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(alerts_frame, text="Alert on Insufficient Balance", variable=self.alert_insufficient_balance_var).pack(anchor='w', pady=2)

        # Telegram Heartbeat
        heartbeat_container = ttk.Frame(alerts_frame)
        heartbeat_container.pack(fill='x', pady=5)

        self.enable_telegram_heartbeat_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            heartbeat_container,
            text="Telegram Heartbeat every",
            variable=self.enable_telegram_heartbeat_var
        ).pack(side='left')

        self.telegram_heartbeat_var = tk.DoubleVar(value=1.0)
        ttk.Entry(heartbeat_container, textvariable=self.telegram_heartbeat_var, width=8).pack(side='left', padx=5)
        ttk.Label(heartbeat_container, text="hours").pack(side='left')
        ToolTip(heartbeat_container, "Send 'I'm alive' message periodically.\n\nDefault: 1.0 hour\nUncheck to disable heartbeat")
        
        # === Intervals Section ===
        intervals_frame = ttk.LabelFrame(scrollable_frame, text="Scan Intervals", padding=10)
        intervals_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(intervals_frame, text="Market Scan Interval (seconds):").grid(row=0, column=0, sticky='w', pady=5)
        self.market_scan_interval_var = tk.DoubleVar(value=9.0)
        ttk.Entry(intervals_frame, textvariable=self.market_scan_interval_var, width=10).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        ToolTip(intervals_frame.winfo_children()[-1], "How often to scan for new markets.\n\nDefault: 9 seconds\nShorter = faster discovery, more API calls")
        
        ttk.Label(intervals_frame, text="Fill Check Interval (seconds):").grid(row=1, column=0, sticky='w', pady=5)
        self.fill_check_interval_var = tk.DoubleVar(value=9.0)
        ttk.Entry(intervals_frame, textvariable=self.fill_check_interval_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(intervals_frame.winfo_children()[-1], "How often to check if orders are filled.\n\nDefault: 9 seconds\nShorter = faster response, more API calls")

        return frame
        
    def browse_log_file(self):
        """Browse for log file location."""
        filename = filedialog.asksaveasfilename(
            title="Select Log File",
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")]
        )
        if filename:
            self.log_file_var.set(filename)
            
    def create_credentials_tab(self) -> ttk.Frame:
        """Create Credentials & API tab."""
        frame = ttk.Frame(self.notebook)
        scrollable_frame = self.create_scrollable_frame(frame)
        
        # Warning label at top
        warning_label = ttk.Label(
            scrollable_frame,
            text="⚠️  SECURITY WARNING: Never share your private key! Credentials are saved to .env file (not exported to JSON).",
            foreground="red",
            wraplength=700,
            font=("TkDefaultFont", 9, "bold")
        )
        warning_label.pack(fill='x', padx=10, pady=10)
        
        # === Opinion.trade API Section ===
        api_frame = ttk.LabelFrame(scrollable_frame, text="Opinion.trade API", padding=10)
        api_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(api_frame, text="API Key:").grid(row=0, column=0, sticky='w', pady=5)
        self.api_key_var = tk.StringVar(value="")
        self.api_key_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, width=40, show="*")
        self.api_key_entry.grid(row=0, column=1, sticky='w', pady=5, padx=5)

        self.api_key_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(api_frame, text="Show", variable=self.api_key_show_var, command=self.toggle_api_key_visibility).grid(row=0, column=2, pady=5)

        # Help link for API Key
        api_help_label = tk.Label(
            api_frame,
            text="📖 Don't have an API Key? Click here to request access",
            foreground="blue",
            cursor="hand2",
            font=("TkDefaultFont", 9, "underline")
        )
        api_help_label.grid(row=1, column=1, columnspan=2, sticky='w', pady=(0, 5))
        api_help_label.bind("<Button-1>", lambda e: self.open_api_key_request_form())
        ToolTip(api_help_label, "Opens Opinion.trade API access request form in your browser.\n\nFill the form to request API access from the Opinion.trade team.")

        ttk.Label(api_frame, text="Private Key:").grid(row=2, column=0, sticky='w', pady=5)
        self.private_key_var = tk.StringVar(value="")
        self.private_key_entry = ttk.Entry(api_frame, textvariable=self.private_key_var, width=40, show="*")
        self.private_key_entry.grid(row=2, column=1, sticky='w', pady=5, padx=5)

        self.private_key_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(api_frame, text="Show", variable=self.private_key_show_var, command=self.toggle_private_key_visibility).grid(row=2, column=2, pady=5)

        ttk.Label(api_frame, text="Multi-sig Address:").grid(row=3, column=0, sticky='w', pady=5)
        self.multi_sig_var = tk.StringVar(value="")
        ttk.Entry(api_frame, textvariable=self.multi_sig_var, width=40).grid(row=3, column=1, sticky='w', pady=5, padx=5)
        ToolTip(api_frame.winfo_children()[-1], "Multi-signature wallet address.\n\nLeave empty for READ-ONLY mode (no trading)\nRequired for live trading")

        # API Host with lock
        self.enable_api_host_edit_var = tk.BooleanVar(value=False)
        cb_api_host = ttk.Checkbutton(
            api_frame,
            text="⚠️ Edit API Host (Advanced)",
            variable=self.enable_api_host_edit_var,
            command=self.on_api_host_toggle
        )
        cb_api_host.grid(row=4, column=0, columnspan=3, sticky='w', pady=5)
        ToolTip(cb_api_host, "⚠️ WARNING: Don't change unless instructed!\n\nDefault API host works for everyone.\nChanging this may break connectivity.")

        ttk.Label(api_frame, text="API Host:").grid(row=5, column=0, sticky='w', pady=5)
        self.api_host_var = tk.StringVar(value="https://proxy.opinion.trade:8443")
        self.api_host_entry = ttk.Entry(api_frame, textvariable=self.api_host_var, width=40, state='disabled')
        self.api_host_entry.grid(row=5, column=1, sticky='w', pady=5, padx=5)
        ToolTip(self.api_host_entry, "Opinion.trade API endpoint.\n\nDefault: https://proxy.opinion.trade:8443\nDon't change unless instructed")
        
        # === Telegram Section ===
        telegram_frame = ttk.LabelFrame(scrollable_frame, text="Telegram Notifications", padding=10)
        telegram_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(telegram_frame, text="Bot Token:").grid(row=0, column=0, sticky='w', pady=5)
        self.telegram_token_var = tk.StringVar(value="")
        self.telegram_token_entry = ttk.Entry(telegram_frame, textvariable=self.telegram_token_var, width=40, show="*")
        self.telegram_token_entry.grid(row=0, column=1, sticky='w', pady=5, padx=5)

        self.telegram_token_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(telegram_frame, text="Show", variable=self.telegram_token_show_var, command=self.toggle_telegram_token_visibility).grid(row=0, column=2, pady=5)

        # Help link for Telegram setup
        telegram_help_label = tk.Label(
            telegram_frame,
            text="📖 Need help setting up Telegram? Click here for step-by-step guide",
            foreground="blue",
            cursor="hand2",
            font=("TkDefaultFont", 9, "underline")
        )
        telegram_help_label.grid(row=1, column=1, columnspan=2, sticky='w', pady=(0, 5))
        telegram_help_label.bind("<Button-1>", lambda e: self.open_telegram_setup_guide())
        ToolTip(telegram_help_label, "Opens Telegram setup guide with detailed instructions.\n\nShows how to:\n- Create a Telegram bot with @BotFather\n- Get your Chat ID\n- Test notifications")

        ttk.Label(telegram_frame, text="Chat ID:").grid(row=2, column=0, sticky='w', pady=5)
        self.telegram_chat_id_var = tk.StringVar(value="")
        ttk.Entry(telegram_frame, textvariable=self.telegram_chat_id_var, width=40).grid(row=2, column=1, sticky='w', pady=5, padx=5)
        ToolTip(telegram_frame.winfo_children()[-1], "Your Telegram chat ID.\n\nCan be numeric or @username\nLeave empty to disable Telegram")

        ttk.Button(telegram_frame, text="Test Telegram", command=self.test_telegram).grid(row=3, column=1, sticky='w', pady=5)
        
        # === Blockchain Section ===
        blockchain_frame = ttk.LabelFrame(scrollable_frame, text="Blockchain RPC (Advanced)", padding=10)
        blockchain_frame.pack(fill='x', padx=10, pady=5)

        # RPC URL with lock
        self.enable_rpc_edit_var = tk.BooleanVar(value=False)
        cb_rpc = ttk.Checkbutton(
            blockchain_frame,
            text="⚠️ Edit RPC URL (Advanced)",
            variable=self.enable_rpc_edit_var,
            command=self.on_rpc_toggle
        )
        cb_rpc.grid(row=0, column=0, columnspan=3, sticky='w', pady=5)
        ToolTip(cb_rpc, "⚠️ WARNING: Don't change unless you need custom RPC!\n\nDefault BSC RPC works for everyone.\nOnly change if using private RPC node.")

        ttk.Label(blockchain_frame, text="RPC URL:").grid(row=1, column=0, sticky='w', pady=5)
        self.rpc_url_var = tk.StringVar(value="https://bsc-dataseed.binance.org")
        self.rpc_url_entry = ttk.Entry(blockchain_frame, textvariable=self.rpc_url_var, width=40, state='disabled')
        self.rpc_url_entry.grid(row=1, column=1, sticky='w', pady=5, padx=5)
        ToolTip(self.rpc_url_entry, "BSC RPC endpoint.\n\nDefault: https://bsc-dataseed.binance.org\nUsed for blockchain interactions")

        ttk.Label(blockchain_frame, text="Chain ID:").grid(row=2, column=0, sticky='w', pady=5)
        ttk.Label(blockchain_frame, text="56 (BSC Mainnet)", foreground="gray").grid(row=2, column=1, sticky='w', pady=5, padx=5)
        
        return frame
        
    def toggle_api_key_visibility(self):
        """Toggle API key visibility."""
        toggle_field_visibility(self.api_key_show_var, self.api_key_entry)

    def toggle_private_key_visibility(self):
        """Toggle private key visibility."""
        toggle_field_visibility(self.private_key_show_var, self.private_key_entry)

    def toggle_telegram_token_visibility(self):
        """Toggle Telegram token visibility."""
        toggle_field_visibility(self.telegram_token_show_var, self.telegram_token_entry)

    def on_api_host_toggle(self):
        """Handle API host edit toggle."""
        toggle_widget_state(self.enable_api_host_edit_var, self.api_host_entry)

    def on_rpc_toggle(self):
        """Handle RPC URL edit toggle."""
        toggle_widget_state(self.enable_rpc_edit_var, self.rpc_url_entry)

    def open_api_key_request_form(self):
        """Open Opinion.trade API access request form in browser."""
        url = "https://docs.google.com/forms/d/1h7gp8UffZeXzYQ-lv4jcou9PoRNOqMAQhyW4IwZDnII"
        try:
            webbrowser.open(url)
            self.update_status_bar("📖 Opened API Key request form in browser")
            messagebox.showinfo(
                "API Key Request",
                "The API access request form has been opened in your browser.\n\n"
                "Please fill out the form to request API access from the Opinion.trade team.\n\n"
                "You should receive your API key via email after your request is approved."
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open browser:\n{e}\n\nPlease visit manually:\n{url}")

    def open_telegram_setup_guide(self):
        """Open Telegram setup guide."""
        # Try to open local file first, fallback to GitHub
        local_guide = Path("TELEGRAM_SETUP.md")
        github_url = "https://github.com/KrisGravedigger/idk-about-your-opinion-bot/blob/main/TELEGRAM_SETUP.md"

        try:
            if local_guide.exists():
                # Open in default markdown viewer or text editor
                if sys.platform == 'win32':
                    os.startfile(str(local_guide))
                elif sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', str(local_guide)])
                else:  # Linux
                    subprocess.run(['xdg-open', str(local_guide)])
                self.update_status_bar("📖 Opened Telegram setup guide")
            else:
                # Fallback to GitHub
                webbrowser.open(github_url)
                self.update_status_bar("📖 Opened Telegram setup guide in browser")
        except Exception as e:
            # Last resort: open GitHub URL
            try:
                webbrowser.open(github_url)
                self.update_status_bar("📖 Opened Telegram setup guide in browser")
            except:
                messagebox.showerror(
                    "Error",
                    f"Failed to open Telegram setup guide.\n\n"
                    f"Please visit manually:\n{github_url}\n\n"
                    f"Or check TELEGRAM_SETUP.md in the installation folder."
                )

    def setup_launcher_section(self):
        """Create bot launcher controls."""
        launcher_frame = ttk.LabelFrame(self.right_column, text="Bot Control & Output", padding=10)
        
        # Buttons row
        button_frame = ttk.Frame(launcher_frame)
        button_frame.pack(fill='x', pady=5)
        
        self.start_button = ttk.Button(
            button_frame, 
            text="▶ Start Bot", 
            command=self.start_bot,
            width=15
        )
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(
            button_frame, 
            text="⏹ Stop Bot", 
            command=self.stop_bot,
            width=15,
            state='disabled'
        )
        self.stop_button.pack(side='left', padx=5)
        
        self.restart_button = ttk.Button(
            button_frame,
            text="🔄 Restart",
            command=self.restart_bot,
            width=15
        )
        self.restart_button.pack(side='left', padx=5)

        # Info label for Restart button
        restart_info = ttk.Label(button_frame, text="ℹ️ GUI settings override config.py",
                                foreground="blue", font=("TkDefaultFont", 8, "italic"))
        restart_info.pack(side='left', padx=5)

        # Status row
        status_frame = ttk.Frame(launcher_frame)
        status_frame.pack(fill='x', pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side='left', padx=5)
        self.bot_status_label = ttk.Label(status_frame, text="⚪ Stopped", foreground="gray")
        self.bot_status_label.pack(side='left', padx=5)
        
        ttk.Label(status_frame, text="|").pack(side='left', padx=5)
        ttk.Label(status_frame, text="PID:").pack(side='left', padx=5)
        self.pid_label = ttk.Label(status_frame, text="--")
        self.pid_label.pack(side='left', padx=5)
        
        ttk.Label(status_frame, text="|").pack(side='left', padx=5)
        ttk.Label(status_frame, text="Runtime:").pack(side='left', padx=5)
        self.runtime_label = ttk.Label(status_frame, text="--")
        self.runtime_label.pack(side='left', padx=5)
        
        # Utility buttons row
        util_frame = ttk.Frame(launcher_frame)
        util_frame.pack(fill='x', pady=5)
        
        ttk.Button(
            util_frame, 
            text="📊 View Logs", 
            command=self.view_logs,
            width=15
        ).pack(side='left', padx=5)
        
        ttk.Button(
            util_frame,
            text="📁 Open Folder",
            command=self.open_folder,
            width=15
        ).pack(side='left', padx=5)

        ttk.Button(
            util_frame,
            text="🗑️ Clear Logs",
            command=self.clear_log_viewer,
            width=15
        ).pack(side='left', padx=5)

        ttk.Button(
            util_frame,
            text="📊 View PnL",
            command=self.view_transaction_history,
            width=15
        ).pack(side='left', padx=5)

        ttk.Button(
            util_frame,
            text="📋 View State",
            command=self.view_state_file,
            width=15
        ).pack(side='left', padx=5)

        # Real-time log viewer
        log_viewer_frame = ttk.LabelFrame(launcher_frame, text="Real-Time Bot Output", padding=5)
        log_viewer_frame.pack(fill='both', expand=True, pady=(10, 0))

        # Auto-scroll toggle
        autoscroll_frame = ttk.Frame(log_viewer_frame)
        autoscroll_frame.pack(fill='x', pady=(0, 5))

        self.auto_scroll_var = tk.BooleanVar(value=True)
        cb_autoscroll = ttk.Checkbutton(
            autoscroll_frame,
            text="Auto-scroll to bottom",
            variable=self.auto_scroll_var,
            command=self.on_autoscroll_toggle
        )
        cb_autoscroll.pack(side='left')

        self.log_viewer = scrolledtext.ScrolledText(
            log_viewer_frame,
            height=15,
            wrap='word',
            font=('Consolas', 9) if sys.platform == 'win32' else ('Courier', 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white',
            state='disabled'
        )
        self.log_viewer.pack(fill='both', expand=True)

        # Configure text tags for colored output
        self.log_viewer.tag_config('timestamp', foreground='#808080')
        self.log_viewer.tag_config('info', foreground='#4ec9b0')
        self.log_viewer.tag_config('warning', foreground='#dcdcaa')
        self.log_viewer.tag_config('error', foreground='#f48771')
        self.log_viewer.tag_config('success', foreground='#b5cea8')

        launcher_frame.pack(fill='both', expand=True)
        
    def setup_action_buttons(self):
        """Create action buttons section."""
        action_frame = ttk.Frame(self.left_column)
        action_frame.pack(fill='x', padx=5, pady=5)

        # Row 1: Main actions
        row1 = ttk.Frame(action_frame)
        row1.pack(fill='x', pady=2)

        ttk.Button(row1, text="💾 Save Configuration", command=self.save_configuration, width=20).pack(side='left', padx=2)
        ttk.Button(row1, text="📤 Export", command=self.export_configuration, width=15).pack(side='left', padx=2)
        ttk.Button(row1, text="📥 Import", command=self.import_configuration, width=15).pack(side='left', padx=2)

        # Info label for Import button
        import_info = ttk.Label(row1, text="ℹ️ After importing, save config and restart bot to apply changes",
                               foreground="blue", font=("TkDefaultFont", 8, "italic"))
        import_info.pack(side='left', padx=5)

        # Row 2: Advanced actions
        row2 = ttk.Frame(action_frame)
        row2.pack(fill='x', pady=2)

        ttk.Button(row2, text="🔧 Test Configuration", command=self.test_configuration, width=20).pack(side='left', padx=2)
        ttk.Button(row2, text="📁 Manage Profiles", command=self.manage_profiles, width=20).pack(side='left', padx=2)
        
    def setup_status_bar(self):
        """Create status bar."""
        self.status_bar = ttk.Label(
            self.root, 
            text="Ready", 
            relief=tk.SUNKEN, 
            anchor='w',
            padding=5
        )
        self.status_bar.pack(side='bottom', fill='x')
        
    def update_status_bar(self, message: str):
        """Update status bar with message."""
        self.status_bar.config(text=message)
        self.root.update_idletasks()
        
    def load_configuration(self):
        """Load configuration from bot_config.json or defaults from config.py."""
        try:
            config_file = Path("bot_config.json")

            if config_file.exists():
                self.config_data = load_json_file(config_file)
                self.update_status_bar("✅ Loaded configuration from bot_config.json")
            else:
                # Load defaults from config.py
                self.config_data = self.extract_config_from_module(config_py)
                self.update_status_bar("ℹ️ Loaded defaults from config.py")
            
            # Load credentials from .env
            # IMPORTANT: Only load from current directory, not parent directories
            # This prevents accidentally loading developer's real credentials during testing
            from dotenv import load_dotenv
            env_file = Path(".env")
            if env_file.exists():
                load_dotenv(dotenv_path=env_file, verbose=False)

            self.api_key_var.set(os.getenv("API_KEY", ""))
            self.private_key_var.set(os.getenv("PRIVATE_KEY", ""))
            self.multi_sig_var.set(os.getenv("MULTI_SIG_ADDRESS", ""))
            self.rpc_url_var.set(os.getenv("RPC_URL", "https://bsc-dataseed.binance.org"))
            self.telegram_token_var.set(os.getenv("TELEGRAM_BOT_TOKEN", ""))
            self.telegram_chat_id_var.set(os.getenv("TELEGRAM_CHAT_ID", ""))
            
            # Populate form fields
            self.populate_form_fields()
            
            self.config_changed = False
            
        except Exception as e:
            messagebox.showerror("Error Loading Configuration", f"Failed to load configuration:\n\n{str(e)}")
            
    def extract_config_from_module(self, module) -> dict:
        """Extract configuration values from config.py module."""
        config_dict = {}
        
        # List of config keys to extract
        keys = [
            'CAPITAL_MODE', 'CAPITAL_PERCENTAGE', 'CAPITAL_AMOUNT_USDT',
            'AUTO_REINVEST', 'MIN_BALANCE_TO_CONTINUE_USDT', 'MIN_POSITION_SIZE_USDT',
            'DUST_THRESHOLD', 'SCORING_PROFILE', 'BONUS_MARKETS_FILE', 'BONUS_MULTIPLIER',
            'MIN_ORDERBOOK_ORDERS', 'OUTCOME_MIN_PROBABILITY', 'OUTCOME_MAX_PROBABILITY',
            'MIN_HOURS_UNTIL_CLOSE', 'MAX_HOURS_UNTIL_CLOSE',
            'SPREAD_THRESHOLD_1', 'SPREAD_THRESHOLD_2', 'SPREAD_THRESHOLD_3',
            'IMPROVEMENT_TINY', 'IMPROVEMENT_SMALL', 'IMPROVEMENT_MEDIUM', 'IMPROVEMENT_WIDE',
            'SAFETY_MARGIN_CENTS', 'PRICE_DECIMALS', 'AMOUNT_DECIMALS',
            'ENABLE_STOP_LOSS', 'STOP_LOSS_TRIGGER_PERCENT', 'STOP_LOSS_AGGRESSIVE_OFFSET',
            'LIQUIDITY_AUTO_CANCEL', 'LIQUIDITY_BID_DROP_THRESHOLD', 'LIQUIDITY_SPREAD_THRESHOLD',
            'BUY_ORDER_TIMEOUT_HOURS', 'SELL_ORDER_TIMEOUT_HOURS',
            'ENABLE_SELL_ORDER_REPRICING', 'SELL_REPRICE_LIQUIDITY_THRESHOLD_PCT',
            'ALLOW_SELL_BELOW_BUY_PRICE', 'MAX_SELL_PRICE_REDUCTION_PCT',
            'SELL_REPRICE_SCALE_MODE', 'SELL_REPRICE_LIQUIDITY_TARGET_PCT',
            'SELL_REPRICE_LIQUIDITY_RETURN_PCT', 'ENABLE_DYNAMIC_SELL_PRICE_ADJUSTMENT',
            'LOG_LEVEL', 'LOG_FILE',
            'MARKET_SCAN_INTERVAL_SECONDS', 'FILL_CHECK_INTERVAL_SECONDS',
            'TELEGRAM_HEARTBEAT_INTERVAL_HOURS',
            'API_HOST'
        ]
        
        for key in keys:
            if hasattr(module, key):
                config_dict[key.lower()] = getattr(module, key)
                
        return config_dict
        
    def populate_form_fields(self):
        """Populate form fields from config_data."""
        # Capital tab
        self.capital_mode_var.set(self.config_data.get('capital_mode', 'percentage'))
        self.capital_percentage_var.set(self.config_data.get('capital_percentage', 90.0))
        self.capital_amount_var.set(self.config_data.get('capital_amount_usdt', 20.0))
        self.auto_reinvest_var.set(self.config_data.get('auto_reinvest', True))
        self.min_balance_var.set(self.config_data.get('min_balance_to_continue_usdt', 60.0))
        self.min_position_var.set(self.config_data.get('min_position_size_usdt', 50.0))
        self.dust_threshold_var.set(self.config_data.get('dust_threshold', 30.0))
        self.on_capital_mode_change()
        
        # Market tab
        self.scoring_profile_var.set(self.config_data.get('scoring_profile', 'production_farming'))
        self.bonus_file_var.set(self.config_data.get('bonus_markets_file', ''))
        self.bonus_multiplier_var.set(self.config_data.get('bonus_multiplier', 1.0))
        self.min_orderbook_var.set(self.config_data.get('min_orderbook_orders', 1))
        self.outcome_min_prob_var.set(self.config_data.get('outcome_min_probability', 0.20))
        self.outcome_max_prob_var.set(self.config_data.get('outcome_max_probability', 0.90))
        self.min_hours_var.set(str(self.config_data.get('min_hours_until_close', '') if self.config_data.get('min_hours_until_close') else ''))
        self.max_hours_var.set(str(self.config_data.get('max_hours_until_close', 168)))
        self.on_scoring_profile_change()
        
        # Trading tab
        self.spread_threshold_1_var.set(self.config_data.get('spread_threshold_1', 0.20))
        self.spread_threshold_2_var.set(self.config_data.get('spread_threshold_2', 0.50))
        self.spread_threshold_3_var.set(self.config_data.get('spread_threshold_3', 1.00))
        self.improvement_tiny_var.set(self.config_data.get('improvement_tiny', 0.00))
        self.improvement_small_var.set(self.config_data.get('improvement_small', 0.10))
        self.improvement_medium_var.set(self.config_data.get('improvement_medium', 0.20))
        self.improvement_wide_var.set(self.config_data.get('improvement_wide', 0.30))
        self.safety_margin_var.set(self.config_data.get('safety_margin_cents', 0.001))
        self.price_decimals_var.set(self.config_data.get('price_decimals', 3))
        self.amount_decimals_var.set(self.config_data.get('amount_decimals', 2))
        
        # Risk tab
        self.enable_stop_loss_var.set(self.config_data.get('enable_stop_loss', True))
        self.stop_loss_trigger_var.set(self.config_data.get('stop_loss_trigger_percent', -10.0))
        self.stop_loss_offset_var.set(self.config_data.get('stop_loss_aggressive_offset', 0.001))
        self.liquidity_auto_cancel_var.set(self.config_data.get('liquidity_auto_cancel', True))
        self.liquidity_bid_drop_var.set(self.config_data.get('liquidity_bid_drop_threshold', 25.0))
        self.liquidity_spread_var.set(self.config_data.get('liquidity_spread_threshold', 15.0))
        self.buy_timeout_var.set(self.config_data.get('buy_order_timeout_hours', 8.0))
        self.sell_timeout_var.set(self.config_data.get('sell_order_timeout_hours', 8.0))

        # Sell Order Repricing
        self.enable_sell_repricing_var.set(self.config_data.get('enable_sell_order_repricing', True))
        self.sell_reprice_threshold_var.set(self.config_data.get('sell_reprice_liquidity_threshold_pct', 50.0))
        self.allow_below_buy_var.set(self.config_data.get('allow_sell_below_buy_price', False))
        self.max_sell_reduction_var.set(self.config_data.get('max_sell_price_reduction_pct', 5.0))
        self.reprice_scale_mode_var.set(self.config_data.get('sell_reprice_scale_mode', 'best'))
        self.liq_target_var.set(self.config_data.get('sell_reprice_liquidity_target_pct', 30.0))
        self.liq_return_var.set(self.config_data.get('sell_reprice_liquidity_return_pct', 20.0))
        self.enable_dynamic_adjustment_var.set(self.config_data.get('enable_dynamic_sell_price_adjustment', True))

        self.on_stop_loss_toggle()
        self.on_sell_repricing_toggle()
        self.on_allow_below_buy_toggle()
        self.on_reprice_mode_change()
        
        # Monitoring tab
        self.log_level_var.set(self.config_data.get('log_level', 'INFO'))
        self.log_file_var.set(self.config_data.get('log_file', 'logs/idk_bot.log'))
        self.alert_order_filled_var.set(self.config_data.get('alert_on_order_filled', True))
        self.alert_position_closed_var.set(self.config_data.get('alert_on_position_closed', True))
        self.alert_error_var.set(self.config_data.get('alert_on_error', True))
        self.alert_insufficient_balance_var.set(self.config_data.get('alert_on_insufficient_balance', True))
        self.market_scan_interval_var.set(self.config_data.get('market_scan_interval_seconds', 9.0))
        self.fill_check_interval_var.set(self.config_data.get('fill_check_interval_seconds', 9.0))
        self.telegram_heartbeat_var.set(self.config_data.get('telegram_heartbeat_interval_hours', 1.0))
        
        # Credentials tab
        self.api_host_var.set(self.config_data.get('api_host', 'https://proxy.opinion.trade:8443'))

    def check_first_run_and_setup(self):
        """
        Check if this is first run and generate necessary files.
        Called during GUI startup before loading configuration.
        """
        first_run = False

        # 1. Check and create .env from .env.example
        if not Path(".env").exists():
            first_run = True
            print("ℹ️  First run detected - creating .env from template...")

            if Path(".env.example").exists():
                shutil.copy(".env.example", ".env")
                print("✅ Created .env from .env.example")
            else:
                # Fallback: create minimal .env if template missing
                self.create_minimal_env()

        # 2. Check and create bonus_markets.txt
        if not Path("bonus_markets.txt").exists():
            print("ℹ️  Creating empty bonus_markets.txt...")

            # Check if there's an example file
            if Path("bonus_markets.txt.example").exists():
                shutil.copy("bonus_markets.txt.example", "bonus_markets.txt")
                print("✅ Created bonus_markets.txt from example")
            else:
                # Create empty file with template
                Path("bonus_markets.txt").write_text(
                    "# Bonus Market Addresses (one per line)\n"
                    "# Example: 0x1234567890abcdef...\n"
                    "# These markets get priority scoring.\n\n"
                )
                print("✅ Created empty bonus_markets.txt")

        # 3. Check and create bot_config.json if missing
        if not Path("bot_config.json").exists():
            print("ℹ️  Creating default bot_config.json...")
            # Use existing extract_config_from_module method
            default_config = self.extract_config_from_module(config_py)
            save_config_to_json(default_config, "bot_config.json")
            print("✅ Created bot_config.json with defaults")

        # 4. Show welcome wizard if first run
        if first_run:
            # Schedule the wizard to show after GUI is fully initialized
            self.root.after(1000, self.show_first_run_wizard)

        return first_run

    def create_minimal_env(self):
        """Create minimal .env file with placeholders."""
        minimal_env = """# Opinion Trading Bot - Environment Variables
# Fill in your values below:

# Opinion.trade API Key
# Get this from your account settings on Opinion.trade
API_KEY=your_api_key_here

# Your wallet's private key (64 hex characters, with or without 0x prefix)
# NEVER share this! Anyone with this key can drain your wallet.
PRIVATE_KEY=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef

# Your wallet address (if using Gnosis Safe, use Safe address)
MULTI_SIG_ADDRESS=0xYourWalletAddressHere

# RPC URL for BNB Chain (optional, default is public Binance node)
RPC_URL=https://bsc-dataseed.binance.org

# Telegram Notifications (optional)
# Get bot token from @BotFather on Telegram
# Get chat ID from @userinfobot
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
"""
        Path(".env").write_text(minimal_env)
        print("✅ Created .env with template values")

    def show_first_run_wizard(self):
        """Show welcome wizard for first-time users."""
        welcome_msg = """🎉 Welcome to Opinion Trading Bot!

This appears to be your first time running the bot.

I've created the following files for you:
  • .env - Store your API keys and credentials here
  • bonus_markets.txt - Optional list of bonus markets
  • bot_config.json - Bot configuration

Next steps:
1. Go to the 🔐 Credentials tab
2. Enter your API Key, Private Key, and Wallet Address
3. (Optional) Configure Telegram notifications
4. Click 💾 Save Configuration
5. Adjust settings in other tabs (Capital, Markets, Trading, Risk)
6. Click ▶ Start Bot

Would you like to open the Credentials tab now?"""

        if messagebox.askyesno("Welcome to Opinion Trading Bot!", welcome_msg):
            # Switch to Credentials tab (index 5 - 0-indexed, last tab)
            self.notebook.select(5)
            self.update_status_bar("ℹ️  Please configure your credentials in the Credentials tab")

    def get_current_version(self) -> str:
        """Get current bot version from version.txt file."""
        version_file = Path("version.txt")
        if version_file.exists():
            try:
                return version_file.read_text().strip()
            except Exception as e:
                print(f"Warning: Could not read version.txt: {e}")
                return self.VERSION  # Fallback
        return self.VERSION  # Fallback if file doesn't exist

    def check_for_updates(self):
        """
        Check GitHub for new releases (runs in background thread).
        Non-blocking - shows notification if update available.
        """
        try:
            import requests

            current_version = self.get_current_version()

            # GitHub API endpoint for latest release
            # Replace YOUR_USERNAME with actual GitHub username
            api_url = "https://api.github.com/repos/KrisGravedigger/idk-about-your-opinion-bot/releases/latest"

            response = requests.get(api_url, timeout=5)

            if response.status_code != 200:
                # Silently fail - don't annoy user if GitHub is down
                print(f"Update check: GitHub API returned {response.status_code}")
                return

            data = response.json()
            latest_version = data.get("tag_name", "").lstrip("v")  # Remove 'v' prefix

            if not latest_version:
                print("Update check: No version tag found in release")
                return

            # Compare versions
            if version.parse(latest_version) > version.parse(current_version):
                # New version available!
                download_url = data.get("html_url")  # Link to release page

                # Show notification in GUI thread
                self.root.after(0, lambda: self.show_update_notification(
                    latest_version,
                    current_version,
                    download_url
                ))
            else:
                print(f"Update check: Already on latest version (v{current_version})")

        except requests.exceptions.RequestException as e:
            # Network error - silently fail
            print(f"Update check failed (network): {e}")
        except Exception as e:
            # Silently fail - don't interrupt user experience
            print(f"Update check failed: {e}")

    def show_update_notification(self, new_version: str, current_version: str, download_url: str):
        """Show update notification dialog."""
        msg = f"""🎉 New Version Available!

Current Version: v{current_version}
Latest Version: v{new_version}

Would you like to download the update?

Update Instructions:
1. Stop the bot (click ⏹ Stop Bot)
2. Download the new version
3. Extract to this folder (overwrite files)
4. Your settings will be preserved:
   - .env (credentials)
   - state.json (bot state)
   - pnl_stats.json (statistics)
   - bot_config.json (configuration)

Click Yes to open the download page."""

        if messagebox.askyesno("Update Available", msg):
            webbrowser.open(download_url)
            self.update_status_bar(f"🔄 Update available: v{new_version} (opened download page)")
        else:
            self.update_status_bar(f"ℹ️  Update available: v{new_version} (skipped)")

    def collect_form_data(self) -> dict:
        """Collect all form data into a dictionary."""
        data = {}
        
        # Capital tab
        data['capital_mode'] = self.capital_mode_var.get()
        data['capital_percentage'] = self.capital_percentage_var.get()
        data['capital_amount_usdt'] = self.capital_amount_var.get()
        data['auto_reinvest'] = self.auto_reinvest_var.get()
        data['min_balance_to_continue_usdt'] = self.min_balance_var.get()
        data['min_position_size_usdt'] = self.min_position_var.get()
        data['dust_threshold'] = self.dust_threshold_var.get()
        
        # Market tab
        data['scoring_profile'] = self.scoring_profile_var.get()
        
        # Custom scoring weights (if custom profile)
        if data['scoring_profile'] == 'custom':
            data['scoring_weights'] = {
                key: var.get() for key, (var, _) in self.weight_vars.items()
            }
        
        data['bonus_markets_file'] = self.bonus_file_var.get() if self.bonus_file_var.get() else None
        data['bonus_multiplier'] = self.bonus_multiplier_var.get()
        data['min_orderbook_orders'] = self.min_orderbook_var.get()
        data['outcome_min_probability'] = self.outcome_min_prob_var.get()
        data['outcome_max_probability'] = self.outcome_max_prob_var.get()
        
        # Handle None values for hours
        min_hours = self.min_hours_var.get().strip()
        if min_hours and min_hours.lower() != 'none':
            try:
                data['min_hours_until_close'] = float(min_hours)
            except ValueError:
                data['min_hours_until_close'] = None
        else:
            data['min_hours_until_close'] = None

        max_hours = self.max_hours_var.get().strip()
        if max_hours and max_hours.lower() != 'none':
            try:
                data['max_hours_until_close'] = float(max_hours)
            except ValueError:
                data['max_hours_until_close'] = None
        else:
            data['max_hours_until_close'] = None
        
        # Trading tab
        data['spread_threshold_1'] = self.spread_threshold_1_var.get()
        data['spread_threshold_2'] = self.spread_threshold_2_var.get()
        data['spread_threshold_3'] = self.spread_threshold_3_var.get()
        data['improvement_tiny'] = self.improvement_tiny_var.get()
        data['improvement_small'] = self.improvement_small_var.get()
        data['improvement_medium'] = self.improvement_medium_var.get()
        data['improvement_wide'] = self.improvement_wide_var.get()
        data['safety_margin_cents'] = self.safety_margin_var.get()
        data['price_decimals'] = self.price_decimals_var.get()
        data['amount_decimals'] = self.amount_decimals_var.get()
        
        # Risk tab
        data['enable_stop_loss'] = self.enable_stop_loss_var.get()
        data['stop_loss_trigger_percent'] = self.stop_loss_trigger_var.get()
        data['stop_loss_aggressive_offset'] = self.stop_loss_offset_var.get()
        data['liquidity_auto_cancel'] = self.liquidity_auto_cancel_var.get()
        data['liquidity_bid_drop_threshold'] = self.liquidity_bid_drop_var.get()
        data['liquidity_spread_threshold'] = self.liquidity_spread_var.get()
        data['buy_order_timeout_hours'] = self.buy_timeout_var.get()
        data['sell_order_timeout_hours'] = self.sell_timeout_var.get()

        # Sell Order Repricing
        data['enable_sell_order_repricing'] = self.enable_sell_repricing_var.get()
        data['sell_reprice_liquidity_threshold_pct'] = self.sell_reprice_threshold_var.get()
        data['allow_sell_below_buy_price'] = self.allow_below_buy_var.get()
        data['max_sell_price_reduction_pct'] = self.max_sell_reduction_var.get()
        data['sell_reprice_scale_mode'] = self.reprice_scale_mode_var.get()
        data['sell_reprice_liquidity_target_pct'] = self.liq_target_var.get()
        data['sell_reprice_liquidity_return_pct'] = self.liq_return_var.get()
        data['enable_dynamic_sell_price_adjustment'] = self.enable_dynamic_adjustment_var.get()

        # Monitoring tab
        data['log_level'] = self.log_level_var.get()
        data['log_file'] = self.log_file_var.get()
        data['alert_on_order_filled'] = self.alert_order_filled_var.get()
        data['alert_on_position_closed'] = self.alert_position_closed_var.get()
        data['alert_on_error'] = self.alert_error_var.get()
        data['alert_on_insufficient_balance'] = self.alert_insufficient_balance_var.get()
        data['market_scan_interval_seconds'] = self.market_scan_interval_var.get()
        data['fill_check_interval_seconds'] = self.fill_check_interval_var.get()
        data['telegram_heartbeat_interval_hours'] = self.telegram_heartbeat_var.get()
        
        # Credentials tab
        data['api_host'] = self.api_host_var.get()
        
        return data
        
    def save_configuration(self):
        """Save configuration to bot_config.json and .env."""
        try:
            # Check if bot is running and offer save & restart option
            bot_running = self.bot_process and self.bot_process.poll() is None
            should_restart = False

            if bot_running:
                # Create custom dialog with three buttons
                dialog = tk.Toplevel(self.root)
                dialog.title("Bot is Running")
                dialog.geometry("450x200")
                dialog.resizable(False, False)
                dialog.transient(self.root)
                dialog.grab_set()

                # Center the dialog
                dialog.update_idletasks()
                x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
                y = (dialog.winfo_screenheight() // 2) - (200 // 2)
                dialog.geometry(f'450x200+{x}+{y}')

                # Message
                message_frame = ttk.Frame(dialog, padding=20)
                message_frame.pack(fill='both', expand=True)

                ttk.Label(
                    message_frame,
                    text="⚠️ Warning: The bot is currently running!",
                    font=("TkDefaultFont", 10, "bold")
                ).pack(pady=(0, 10))

                ttk.Label(
                    message_frame,
                    text="To apply new settings, the bot needs to be restarted.\n\n"
                         "What would you like to do?",
                    justify='center'
                ).pack(pady=(0, 20))

                # Button frame
                button_frame = ttk.Frame(dialog)
                button_frame.pack(fill='x', padx=20, pady=(0, 20))

                result = {'action': None}

                def on_save_and_restart():
                    result['action'] = 'restart'
                    dialog.destroy()

                def on_save_only():
                    result['action'] = 'save'
                    dialog.destroy()

                def on_cancel():
                    result['action'] = 'cancel'
                    dialog.destroy()

                ttk.Button(
                    button_frame,
                    text="💾🔄 Save & Restart Bot",
                    command=on_save_and_restart,
                    width=20
                ).pack(side='left', padx=5)

                ttk.Button(
                    button_frame,
                    text="💾 Save Only",
                    command=on_save_only,
                    width=15
                ).pack(side='left', padx=5)

                ttk.Button(
                    button_frame,
                    text="❌ Cancel",
                    command=on_cancel,
                    width=10
                ).pack(side='left', padx=5)

                # Wait for user to close dialog
                self.root.wait_window(dialog)

                if result['action'] == 'cancel':
                    self.update_status_bar("❌ Save cancelled")
                    return
                elif result['action'] == 'restart':
                    should_restart = True

            # Collect form data
            config_data = self.collect_form_data()

            # Validate configuration
            if not validate_and_warn(config_data, validate_full_config, "Save configuration"):
                self.update_status_bar("❌ Validation failed or cancelled - configuration not saved")
                return

            # Save bot configuration to JSON
            save_config_to_json(config_data, "bot_config.json")
            
            # Save credentials to .env
            env_vars = {
                'API_KEY': self.api_key_var.get(),
                'PRIVATE_KEY': self.private_key_var.get(),
                'MULTI_SIG_ADDRESS': self.multi_sig_var.get(),
                'RPC_URL': self.rpc_url_var.get(),
                'TELEGRAM_BOT_TOKEN': self.telegram_token_var.get(),
                'TELEGRAM_CHAT_ID': self.telegram_chat_id_var.get(),
            }
            save_env_vars(env_vars, ".env")
            
            self.config_data = config_data
            self.config_changed = False

            # Show success message
            if should_restart:
                messagebox.showinfo("Success", "Configuration saved successfully!\n\nbot_config.json - Bot settings\n.env - Credentials\n\nRestarting bot...")
                self.update_status_bar("✅ Configuration saved - restarting bot...")
                # Restart the bot
                self.restart_bot()
            else:
                messagebox.showinfo("Success", "Configuration saved successfully!\n\nbot_config.json - Bot settings\n.env - Credentials")
                self.update_status_bar("✅ Configuration saved successfully")

        except Exception as e:
            messagebox.showerror("Error Saving Configuration", f"Failed to save configuration:\n\n{str(e)}")
            self.update_status_bar(f"❌ Error saving configuration: {str(e)}")
            
    def export_configuration(self):
        """Export configuration to user-specified file."""
        try:
            # Get save location
            filename = filedialog.asksaveasfilename(
                title="Export Configuration",
                defaultextension=".json",
                initialfile=f"bot_config_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if not filename:
                return
            
            # Collect and validate
            config_data = self.collect_form_data()
            if not validate_and_warn(config_data, validate_full_config, "Export"):
                return
            
            # Save (credentials are NOT included - handled by save_config_to_json)
            save_config_to_json(config_data, filename)
            
            messagebox.showinfo("Success", f"Configuration exported to:\n{filename}\n\nNote: Credentials are NOT included in export (remain in .env)")
            self.update_status_bar(f"✅ Configuration exported to {Path(filename).name}")
            
        except Exception as e:
            messagebox.showerror("Error Exporting", f"Failed to export configuration:\n\n{str(e)}")
            
    def import_configuration(self):
        """Import configuration from JSON file."""
        try:
            # Get file to import
            filename = filedialog.askopenfilename(
                title="Import Configuration",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if not filename:
                return
            
            # Load and validate
            imported_data = load_json_file(Path(filename))

            if not validate_and_warn(imported_data, validate_full_config, "Import"):
                return
            
            # Update config_data and populate form
            self.config_data = imported_data
            self.populate_form_fields()
            self.config_changed = True

            messagebox.showinfo("Import Successful",
                              f"Configuration imported from:\n{filename}\n\n"
                              "Click 'Save Configuration' to apply changes.")
            self.update_status_bar(f"✅ Imported configuration from {Path(filename).name} (not saved yet)")
            
        except json.JSONDecodeError as e:
            messagebox.showerror("Invalid JSON", f"Failed to parse JSON file:\n\n{str(e)}")
        except Exception as e:
            messagebox.showerror("Error Importing", f"Failed to import configuration:\n\n{str(e)}")
            
    def import_from_config_py(self):
        """One-time migration from config.py to bot_config.json."""
        # Show warning
        warning_msg = """⚠️  WARNING: This action will create bot_config.json

This will read all settings from config.py and save them to bot_config.json.

After this, bot_config.json values will OVERRIDE config.py values.

This is recommended as a ONE-TIME migration when you first start using the GUI.

Do you want to proceed?"""
        
        if not messagebox.askyesno("Import from config.py", warning_msg, icon='warning'):
            return
        
        try:
            # Extract config from config.py
            config_data = self.extract_config_from_module(config_py)
            
            # Validate
            if not validate_and_warn(config_data, validate_full_config, "Import"):
                return
            
            # Save to bot_config.json
            save_config_to_json(config_data, "bot_config.json")
            
            # Update form
            self.config_data = config_data
            self.populate_form_fields()
            
            success_msg = """✅ Successfully imported from config.py!

Created: bot_config.json

The bot will now use bot_config.json values (which override config.py).

You can now configure the bot using this GUI.

Note: Credentials remain in .env file (not affected by this import)."""
            
            messagebox.showinfo("Import Successful", success_msg)
            self.update_status_bar("✅ Imported configuration from config.py → bot_config.json")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import from config.py:\n\n{str(e)}")
            
    def new_configuration(self):
        """Create new configuration from defaults."""
        if self.config_changed:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes. Create new configuration anyway?"):
                return
        
        # Load defaults
        self.config_data = self.extract_config_from_module(config_py)
        self.populate_form_fields()
        self.config_changed = True
        
        self.update_status_bar("✨ Created new configuration from defaults")

    def clear_log_viewer(self):
        """Clear the real-time log viewer."""
        self.log_viewer.config(state='normal')
        self.log_viewer.delete('1.0', 'end')
        self.log_viewer.config(state='disabled')
        self.update_status_bar("🗑️ Log viewer cleared")

    def append_to_log_viewer(self, text, tag=None):
        """Append text to log viewer (thread-safe)."""
        def _append():
            self.log_viewer.config(state='normal')
            if tag:
                self.log_viewer.insert('end', text, tag)
            else:
                self.log_viewer.insert('end', text)

            # Only auto-scroll if enabled
            if self.auto_scroll_var.get():
                self.log_viewer.see('end')

            self.log_viewer.config(state='disabled')

        # Call from GUI thread
        self.root.after(0, _append)

    def on_autoscroll_toggle(self):
        """Handle auto-scroll toggle change."""
        if self.auto_scroll_var.get():
            # If re-enabled, scroll to bottom immediately
            self.log_viewer.see('end')
            self.update_status_bar("✅ Auto-scroll enabled")
        else:
            self.update_status_bar("⏸️ Auto-scroll disabled")

    def read_bot_output(self):
        """Background thread that reads bot output from temp files and displays in log viewer."""
        def is_process_running():
            return self.bot_process and self.bot_process.poll() is None

        # Add startup message
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.append_to_log_viewer(f"[{timestamp}] ", 'timestamp')
        self.append_to_log_viewer("Bot started. Reading from log files...\n", 'info')

        # Open files for reading (bot has them open for writing)
        # Use 'tail -f' style reading - read what's available, wait for more
        stdout_pos = 0
        stderr_pos = 0

        import time
        while is_process_running() or stdout_pos < os.path.getsize(self.bot_stdout_path):
            try:
                # Read new content from stdout file
                with open(self.bot_stdout_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(stdout_pos)
                    new_lines = f.readlines()
                    stdout_pos = f.tell()

                    for line in new_lines:
                        if line.strip():  # Skip empty lines
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.append_to_log_viewer(f"[{timestamp}] ", 'timestamp')

                            # Color code based on content
                            line_lower = line.lower()
                            if 'error' in line_lower or 'exception' in line_lower or 'traceback' in line_lower:
                                self.append_to_log_viewer(line, 'error')
                            elif 'warning' in line_lower or 'warn' in line_lower:
                                self.append_to_log_viewer(line, 'warning')
                            elif 'success' in line_lower or '✅' in line or 'completed' in line_lower:
                                self.append_to_log_viewer(line, 'success')
                            elif 'info' in line_lower or '📊' in line or '🔍' in line or '📝' in line:
                                self.append_to_log_viewer(line, 'info')
                            else:
                                self.append_to_log_viewer(line)

                # Read new content from stderr file
                with open(self.bot_stderr_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(stderr_pos)
                    new_lines = f.readlines()
                    stderr_pos = f.tell()

                    for line in new_lines:
                        if line.strip():
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.append_to_log_viewer(f"[{timestamp}] ", 'timestamp')
                            self.append_to_log_viewer(line, 'error')  # stderr is always error

                # Sleep briefly to avoid busy-waiting
                time.sleep(0.1)

            except Exception as e:
                # Log error but don't crash thread
                print(f"Error reading bot output: {e}")
                time.sleep(0.5)

        # Process finished - read any remaining output
        try:
            with open(self.bot_stdout_path, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(stdout_pos)
                remaining = f.read()
                if remaining.strip():
                    for line in remaining.split('\n'):
                        if line.strip():
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.append_to_log_viewer(f"[{timestamp}] {line}\n")

            with open(self.bot_stderr_path, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(stderr_pos)
                remaining = f.read()
                if remaining.strip():
                    for line in remaining.split('\n'):
                        if line.strip():
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            self.append_to_log_viewer(f"[{timestamp}] {line}\n", 'error')
        except:
            pass

        # Add completion message
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.append_to_log_viewer(f"\n[{timestamp}] ", 'timestamp')
        self.append_to_log_viewer("Bot process ended.\n", 'info')

    def start_bot(self):
        """Launch bot as subprocess."""
        if self.bot_process and self.bot_process.poll() is None:
            messagebox.showwarning("Bot Running", "Bot is already running!")
            return
        
        # Check if configuration is saved
        if not Path("bot_config.json").exists() and self.config_changed:
            if messagebox.askyesno("Configuration Not Saved", 
                                  "Configuration has not been saved. Save now before starting bot?"):
                self.save_configuration()
        
        # Validate configuration
        config_data = self.collect_form_data()
        if not validate_and_warn(config_data, validate_full_config, "Start bot"):
            return

        # Validate credentials
        def validate_creds_wrapper(data):
            return validate_credentials(
                self.api_key_var.get(),
                self.private_key_var.get(),
                self.multi_sig_var.get()
            )

        if not validate_and_warn({}, validate_creds_wrapper, "Start bot"):
            return
        
        try:
            # Clear log viewer for new run
            self.clear_log_viewer()

            # Prepare environment with unbuffered output
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Force unbuffered output (immediate logs)
            env['PYTHONIOENCODING'] = 'utf-8'  # Ensure UTF-8 encoding for emojis

            # Create temporary log file for subprocess stdout/stderr
            # This prevents subprocess.PIPE deadlock (pipe buffer fills up and blocks process)
            import tempfile
            self.bot_stdout_file = tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8',
                                                                 delete=False, suffix='_stdout.log')
            self.bot_stderr_file = tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8',
                                                                 delete=False, suffix='_stderr.log')

            # Store file paths for reading
            self.bot_stdout_path = self.bot_stdout_file.name
            self.bot_stderr_path = self.bot_stderr_file.name

            # Launch bot subprocess with stdout/stderr redirected to files
            # This prevents deadlock - no pipe buffer to fill up!
            self.bot_process = subprocess.Popen(
                [sys.executable, "-u", "autonomous_bot_main.py"],  # -u flag for unbuffered Python
                stdout=self.bot_stdout_file,
                stderr=self.bot_stderr_file,
                env=env
            )

            # Monitor bot for early crashes (check every second for 15 seconds)
            def check_bot_startup():
                for i in range(15):  # Check for 15 seconds
                    time.sleep(1)
                    if self.bot_process and self.bot_process.poll() is not None:
                        # Bot crashed!
                        error_msg = f"Bot crashed after ~{i+1} seconds!\n\n"
                        error_msg += f"Exit code: {self.bot_process.returncode}\n\n"
                        error_msg += "Check the log viewer below for error details."

                        # Show error in GUI thread
                        self.root.after(0, lambda msg=error_msg: messagebox.showerror("Bot Crashed", msg))
                        self.root.after(0, lambda s=f"❌ Bot crashed after {i+1}s": self.update_status_bar(s))
                        return

                # After 15 seconds, bot seems stable
                pid = self.bot_process.pid if self.bot_process else 0
                self.root.after(0, lambda p=pid: self.update_status_bar(f"✅ Bot running normally (PID: {p})"))

            # Start monitoring thread
            threading.Thread(target=check_bot_startup, daemon=True).start()

            # Start log reader thread for real-time output
            threading.Thread(target=self.read_bot_output, daemon=True).start()

            # Update UI
            self.start_button.config(state='disabled')
            self.stop_button.config(state='normal')
            self.bot_status_label.config(text="🟢 Running", foreground="green")
            self.pid_label.config(text=str(self.bot_process.pid))

            # Start runtime counter
            self.bot_start_time = time.time()
            self.update_runtime()

            self.update_status_bar(f"✅ Bot started (PID: {self.bot_process.pid}). Monitoring startup...")

        except Exception as e:
            messagebox.showerror("Start Failed", f"Failed to start bot:\n\n{str(e)}")
            self.update_status_bar(f"❌ Failed to start bot: {str(e)}")
            
    def stop_bot(self):
        """Gracefully stop bot subprocess."""
        if not self.bot_process or self.bot_process.poll() is not None:
            messagebox.showinfo("Bot Not Running", "Bot is not running.")
            return
        
        if not messagebox.askyesno("Stop Bot", "Are you sure you want to stop the bot?"):
            return
        
        try:
            # Send SIGTERM for graceful shutdown
            self.bot_process.terminate()
            self.update_status_bar("⏳ Stopping bot gracefully...")
            
            # Wait up to 10 seconds
            try:
                self.bot_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill if still running
                self.bot_process.kill()
                self.bot_process.wait()
                self.update_status_bar("⚠️ Bot force-stopped (did not respond to graceful shutdown)")
            
            # Update UI
            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            self.bot_status_label.config(text="🔴 Stopped", foreground="red")
            self.pid_label.config(text="--")
            self.runtime_label.config(text="--")

            # Send Telegram notification if enabled
            try:
                telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
                telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
                if telegram_token and telegram_chat_id:
                    notifier = TelegramNotifier(telegram_token, telegram_chat_id)
                    runtime = time.time() - self.bot_start_time if self.bot_start_time > 0 else 0
                    runtime_str = f"{int(runtime // 3600)}h {int((runtime % 3600) // 60)}m" if runtime > 0 else "N/A"
                    notifier.send_message(
                        f"🛑 <b>Bot Stopped</b>\n\n"
                        f"⏱ Runtime: {runtime_str}\n"
                        f"📅 Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"<i>Bot was manually stopped via GUI</i>",
                        async_send=True
                    )
            except Exception as e:
                # Don't fail stop operation if notification fails
                pass

            self.update_status_bar("✅ Bot stopped successfully")
            
        except Exception as e:
            messagebox.showerror("Stop Failed", f"Failed to stop bot:\n\n{str(e)}")
            self.update_status_bar(f"❌ Failed to stop bot: {str(e)}")
            
    def restart_bot(self):
        """Restart bot."""
        if self.bot_process and self.bot_process.poll() is None:
            self.stop_bot()
            time.sleep(1)  # Give it a moment
        self.start_bot()
        
    def update_runtime(self):
        """Update runtime display every second."""
        if self.bot_process and self.bot_process.poll() is None:
            elapsed = time.time() - self.bot_start_time
            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.runtime_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # Schedule next update
            self.root.after(1000, self.update_runtime)
        else:
            # Bot stopped
            if self.bot_process:
                self.start_button.config(state='normal')
                self.stop_button.config(state='disabled')
                self.bot_status_label.config(text="🔴 Stopped", foreground="red")
                self.pid_label.config(text="--")
                self.runtime_label.config(text="--")
                
    def check_bot_status(self):
        """Check if bot is running on startup."""
        # This is a simple check - could be enhanced with PID file
        pass
        
    def test_configuration(self):
        """Validate and test current configuration."""
        test_window = tk.Toplevel(self.root)
        test_window.title("Test Configuration")
        test_window.geometry("600x500")
        
        # Results text area
        results_text = scrolledtext.ScrolledText(test_window, wrap=tk.WORD, font=("Consolas", 9))
        results_text.pack(fill='both', expand=True, padx=10, pady=10)

        # Helper to safely write to widget (prevents crash if window closed during test)
        def safe_write(text, tag=None):
            """Safely write to results_text widget, handling window closure."""
            try:
                if results_text.winfo_exists():
                    results_text.insert('end', text, tag) if tag else results_text.insert('end', text)
            except:
                pass  # Widget destroyed - silently ignore

        def run_tests():
            safe_write( "🔧 Testing Configuration...\n")
            safe_write( "=" * 60 + "\n\n")
            
            # Test 1: Validate configuration
            safe_write( "1. Validating configuration...\n")
            config_data = self.collect_form_data()
            is_valid, errors, warnings = validate_full_config(config_data)
            
            if is_valid:
                safe_write( "   ✅ Configuration is valid\n", 'success')
            else:
                safe_write( "   ❌ Configuration has errors:\n", 'error')
                for err in errors:
                    safe_write( f"      • {err}\n", 'error')
            
            if warnings:
                safe_write( "   ⚠️  Warnings:\n", 'warning')
                for warn in warnings:
                    safe_write( f"      • {warn}\n", 'warning')
            
            safe_write( "\n")
            
            # Test 2: Validate credentials
            safe_write( "2. Validating credentials...\n")
            is_valid, errors, warnings = validate_credentials(
                self.api_key_var.get(),
                self.private_key_var.get(),
                self.multi_sig_var.get()
            )
            
            if is_valid:
                safe_write( "   ✅ Credentials are valid\n", 'success')
            else:
                safe_write( "   ❌ Credentials have errors:\n", 'error')
                for err in errors:
                    safe_write( f"      • {err}\n", 'error')
            
            if warnings:
                for warn in warnings:
                    safe_write( f"   ⚠️  {warn}\n", 'warning')
            
            safe_write( "\n")
            
            # Test 3: Check API connectivity
            safe_write( "3. Testing API connectivity...\n")
            api_host = self.api_host_var.get()
            api_key = self.api_key_var.get()

            # Test 3a: Basic connectivity (ping host)
            try:
                import requests
                # Just try to connect to the host
                parsed_url = api_host.replace('https://', '').replace('http://', '').split('/')[0]
                test_url = f"https://{parsed_url}"

                safe_write( f"   Testing connection to {parsed_url}...\n")
                response = requests.get(test_url, timeout=5, verify=False)
                safe_write( f"   ✅ Host is reachable (status {response.status_code})\n", 'success')
            except requests.exceptions.SSLError:
                safe_write( f"   ✅ Host is reachable (SSL cert issue is normal)\n", 'success')
            except requests.exceptions.Timeout:
                safe_write( f"   ❌ Connection timed out\n", 'error')
            except requests.exceptions.ConnectionError as e:
                safe_write( f"   ❌ Cannot connect: {str(e)[:100]}\n", 'error')
            except Exception as e:
                safe_write( f"   ⚠️  Connection test: {str(e)[:100]}\n", 'warning')

            # Test 3b: Try to initialize SDK client (if we have credentials)
            private_key = self.private_key_var.get().strip()
            rpc_url = self.rpc_url_var.get().strip()

            # Debug output
            safe_write( f"   Debug - API key length: {len(api_key) if api_key else 0}\n")
            safe_write( f"   Debug - Private key length: {len(private_key) if private_key else 0}\n")
            safe_write( f"   Debug - RPC URL: {rpc_url[:50] if rpc_url else '(empty)'}...\n")

            if api_key and private_key and rpc_url:
                safe_write( f"   Testing SDK initialization...\n")
                try:
                    # Import SDK
                    from opinion_clob_sdk import Client

                    # Debug: show what we're passing
                    multi_sig = self.multi_sig_var.get().strip()
                    safe_write( f"   Creating client with:\n")
                    safe_write( f"      host={api_host}\n")
                    safe_write( f"      apikey={api_key[:10]}...\n")
                    safe_write( f"      private_key={private_key[:10]}... (len={len(private_key)})\n")
                    safe_write( f"      rpc_url={rpc_url}\n")
                    if multi_sig:
                        safe_write( f"      multi_sig_addr={multi_sig}\n")

                    # Build client parameters
                    client_params = {
                        'host': api_host,
                        'apikey': api_key,
                        'chain_id': 56,
                        'private_key': private_key,
                        'rpc_url': rpc_url
                    }
                    # Add multi_sig_addr only if provided
                    if multi_sig:
                        client_params['multi_sig_addr'] = multi_sig

                    # Try to create client
                    test_client = Client(**client_params)
                    safe_write( f"   ✅ SDK client initialized successfully\n", 'success')

                    # Try to fetch markets
                    safe_write( f"   Fetching markets list...\n")
                    try:
                        from opinion_clob_sdk import TopicStatusFilter
                        response = test_client.get_markets(page=1, limit=1, status=TopicStatusFilter.ACTIVATED)
                        if hasattr(response, 'success') and response.success:
                            safe_write( f"   ✅ API is working! Successfully fetched markets\n", 'success')
                        elif hasattr(response, 'result'):
                            safe_write( f"   ✅ API responded with data\n", 'success')
                        else:
                            safe_write( f"   ⚠️  API responded but format unexpected\n", 'warning')
                    except Exception as e:
                        error_str = str(e)
                        if "401" in error_str or "unauthorized" in error_str.lower():
                            safe_write( f"   ❌ API key is invalid (401 Unauthorized)\n", 'error')
                        else:
                            safe_write( f"   ❌ API call failed: {error_str[:200]}\n", 'error')

                except ImportError:
                    safe_write( f"   ⚠️  opinion_clob_sdk not installed - cannot test API fully\n", 'warning')
                except Exception as e:
                    error_str = str(e)
                    # Show full error for debugging
                    safe_write( f"   ❌ SDK initialization failed:\n", 'error')
                    safe_write( f"      {error_str[:300]}\n", 'error')

                    # Add hints based on error type
                    if "apikey" in error_str.lower():
                        safe_write( f"      💡 Hint: Check API key format\n", 'warning')
                    elif "normalize" in error_str.lower() or "0x" in error_str:
                        safe_write( f"      💡 Hint: Private key must start with '0x'\n", 'warning')
                        safe_write( f"      💡 Hint: RPC URL format: https://... or wss://...\n", 'warning')
                    elif "private" in error_str.lower():
                        safe_write( f"      💡 Hint: Check private key format (must be 66 chars: 0x + 64 hex digits)\n", 'warning')
            elif api_key:
                # Have API key but missing other credentials
                missing = []
                if not private_key:
                    missing.append("Private Key")
                if not rpc_url:
                    missing.append("RPC URL")
                safe_write( f"   ℹ️  Skipping SDK test - missing: {', '.join(missing)}\n", 'info')
            else:
                safe_write( f"   ℹ️  No API key provided - skipping SDK test\n", 'info')
            
            safe_write( "\n")
            
            # Test 4: Check file paths
            safe_write( "4. Checking file paths...\n")
            log_file = Path(self.log_file_var.get())
            safe_write( f"   Log file: {log_file}\n")
            
            if log_file.exists():
                safe_write( f"   ✅ Log file exists ({log_file.stat().st_size} bytes)\n", 'success')
            else:
                safe_write( f"   ℹ️  Log file will be created on first run\n", 'info')
            
            bonus_file = self.bonus_file_var.get()
            if bonus_file:
                if Path(bonus_file).exists():
                    safe_write( f"   ✅ Bonus markets file exists: {bonus_file}\n", 'success')
                else:
                    safe_write( f"   ⚠️  Bonus markets file not found: {bonus_file}\n", 'warning')
            
            safe_write( "\n")
            
            # Summary
            safe_write( "=" * 60 + "\n")
            safe_write( "🎯 Test Complete\n\n")
            
            if is_valid:
                safe_write( "✅ Configuration is ready for use!\n", 'success')
            else:
                results_text.insert('end', "❌ Fix errors before starting bot\n", 'error')
        
        # Configure tags for colors
        results_text.tag_config('success', foreground='green')
        results_text.tag_config('error', foreground='red')
        results_text.tag_config('warning', foreground='orange')
        results_text.tag_config('info', foreground='blue')
        
        # Run tests in thread to keep GUI responsive
        threading.Thread(target=run_tests, daemon=True).start()
        
        # Close button
        ttk.Button(test_window, text="Close", command=test_window.destroy).pack(pady=5)
        
    def test_telegram(self):
        """Test Telegram notification."""
        token = self.telegram_token_var.get()
        chat_id = self.telegram_chat_id_var.get()
        
        if not token or not chat_id:
            messagebox.showwarning("Missing Credentials", "Please enter both Telegram Bot Token and Chat ID")
            return
        
        try:
            import requests
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": "🤖 Test message from Opinion Trading Bot GUI!\n\nIf you received this, Telegram notifications are working correctly."
            }
            
            response = requests.post(url, json=data, timeout=10)
            
            if response.status_code == 200:
                messagebox.showinfo("Success", "✅ Test message sent successfully!\n\nCheck your Telegram for the message.")
                self.update_status_bar("✅ Telegram test successful")
            else:
                messagebox.showerror("Failed", f"❌ Failed to send message.\n\nStatus: {response.status_code}\nResponse: {response.text}")
                self.update_status_bar("❌ Telegram test failed")
                
        except Exception as e:
            messagebox.showerror("Error", f"❌ Failed to send test message:\n\n{str(e)}")
            self.update_status_bar(f"❌ Telegram test error: {str(e)}")
        
    def manage_profiles(self):
        """Open profile management dialog."""
        profile_window = tk.Toplevel(self.root)
        profile_window.title("Manage Profiles")
        profile_window.geometry("500x400")
        
        # Profile list
        list_frame = ttk.Frame(profile_window)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        ttk.Label(list_frame, text="Available Profiles:", font=("TkDefaultFont", 10, "bold")).pack(anchor='w', pady=5)
        
        # Listbox with scrollbar
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')
        
        profile_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=15)
        profile_listbox.pack(fill='both', expand=True)
        scrollbar.config(command=profile_listbox.yview)
        
        # Load profiles
        def refresh_profiles():
            profile_listbox.delete(0, tk.END)
            configs_dir = Path("configs")
            if configs_dir.exists():
                for profile_file in sorted(configs_dir.glob("*.json")):
                    profile_listbox.insert(tk.END, profile_file.name)
        
        refresh_profiles()
        
        # Buttons
        button_frame = ttk.Frame(profile_window)
        button_frame.pack(fill='x', padx=10, pady=5)
        
        def load_selected_profile():
            selection = profile_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a profile to load")
                return
            
            profile_name = profile_listbox.get(selection[0])
            self.load_profile(profile_name)
            profile_window.destroy()
        
        def save_new_profile():
            name = tk.simpledialog.askstring("Save Profile", "Enter profile name:", parent=profile_window)
            if not name:
                return
            
            if not name.endswith('.json'):
                name += '.json'
            
            # Collect current config
            config_data = self.collect_form_data()
            
            # Add profile metadata
            config_data['profile_name'] = name.replace('.json', '').replace('_', ' ').title()
            config_data['profile_description'] = f"Custom profile saved {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Save
            configs_dir = Path("configs")
            configs_dir.mkdir(exist_ok=True)
            
            profile_path = configs_dir / name
            save_config_to_json(config_data, str(profile_path))
            
            messagebox.showinfo("Success", f"Profile saved: {name}")
            refresh_profiles()
        
        def delete_selected_profile():
            selection = profile_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a profile to delete")
                return
            
            profile_name = profile_listbox.get(selection[0])
            
            if not messagebox.askyesno("Confirm Delete", f"Delete profile '{profile_name}'?"):
                return
            
            profile_path = Path("configs") / profile_name
            profile_path.unlink()
            
            messagebox.showinfo("Deleted", f"Profile deleted: {profile_name}")
            refresh_profiles()
        
        ttk.Button(button_frame, text="Load Profile", command=load_selected_profile).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Save Current as New", command=save_new_profile).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Delete", command=delete_selected_profile).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Close", command=profile_window.destroy).pack(side='right', padx=2)
        
    def load_profile(self, profile_name: str):
        """Load a profile from configs/ folder."""
        try:
            profile_path = Path("configs") / profile_name
            
            if not profile_path.exists():
                messagebox.showerror("Profile Not Found", f"Profile file not found: {profile_name}")
                return
            
            profile_data = load_json_file(profile_path)

            # Validate
            if not validate_and_warn(profile_data, validate_full_config, "Load profile"):
                return

            # Load profile
            self.config_data = profile_data
            self.populate_form_fields()
            self.config_changed = True

            msg = f"Loaded profile: {profile_name}\n\n"
            if 'profile_description' in profile_data:
                msg += f"Description: {profile_data['profile_description']}\n\n"
            msg += "Remember to Save Configuration to apply changes."

            messagebox.showinfo("Profile Loaded", msg)
            self.update_status_bar(f"✅ Loaded profile: {profile_name} (not saved yet)")
            
        except Exception as e:
            messagebox.showerror("Error Loading Profile", f"Failed to load profile:\n\n{str(e)}")
            
    def view_logs(self):
        """Open log file in default text editor."""
        log_file = Path(self.log_file_var.get())
        
        if not log_file.exists():
            messagebox.showinfo("No Logs", f"Log file does not exist yet:\n{log_file}\n\nIt will be created when the bot starts.")
            return
        
        try:
            if sys.platform == 'win32':
                os.startfile(log_file)
            elif sys.platform == 'darwin':
                subprocess.run(['open', log_file])
            else:
                subprocess.run(['xdg-open', log_file])
            
            self.update_status_bar(f"📊 Opened log file: {log_file.name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open log file:\n\n{str(e)}")
            
    def open_folder(self):
        """Open project directory in file explorer."""
        try:
            project_dir = Path.cwd()

            if sys.platform == 'win32':
                os.startfile(project_dir)
            elif sys.platform == 'darwin':
                subprocess.run(['open', project_dir])
            else:
                subprocess.run(['xdg-open', project_dir])

            self.update_status_bar("📁 Opened project folder")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder:\n\n{str(e)}")

    def view_transaction_history(self):
        """Open transaction history file in default editor."""
        history_file = Path("transaction_history.json")

        if not history_file.exists():
            messagebox.showinfo(
                "No Transaction History",
                "Transaction history file does not exist yet.\n\n"
                "It will be created when the bot executes its first trade."
            )
            return

        try:
            if sys.platform == 'win32':
                os.startfile(history_file)
            elif sys.platform == 'darwin':
                subprocess.run(['open', history_file])
            else:
                subprocess.run(['xdg-open', history_file])

            self.update_status_bar("📊 Opened transaction history")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open transaction history:\n\n{str(e)}")

    def view_state_file(self):
        """Open bot state file in default editor."""
        state_file = Path("state.json")

        if not state_file.exists():
            messagebox.showinfo(
                "No State File",
                "Bot state file does not exist yet.\n\n"
                "It will be created when the bot starts running."
            )
            return

        try:
            if sys.platform == 'win32':
                os.startfile(state_file)
            elif sys.platform == 'darwin':
                subprocess.run(['open', state_file])
            else:
                subprocess.run(['xdg-open', state_file])

            self.update_status_bar("📋 Opened bot state file")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open state file:\n\n{str(e)}")
            
    def show_documentation(self):
        """Show documentation/README."""
        readme = Path("README.md")
        if readme.exists():
            self.view_logs()  # Use same method to open README
        else:
            messagebox.showinfo("Documentation",
                              f"📚 Opinion Trading Bot v{self.VERSION}\n\n"
                              "For documentation, visit the project repository or README file.\n\n"
                              "Quick Start:\n"
                              "1. Configure credentials in 🔐 Credentials tab\n"
                              "2. Adjust trading parameters in other tabs\n"
                              "3. Test configuration (🔧 button)\n"
                              "4. Save configuration (💾 button)\n"
                              "5. Start bot (▶ button)")
            
    def show_about(self):
        """Show about dialog."""
        about_msg = f"""Opinion Trading Bot - GUI Configurator
Version {self.VERSION}

A graphical interface for configuring and launching 
the autonomous trading bot for Opinion.trade 
prediction markets.

Features:
• 6-tab configuration interface
• Simple bot launcher
• Configuration validation & testing
• Profile management
• Import/export configurations

© 2025 - Automated Trading System
"""
        messagebox.showinfo("About", about_msg)
        
    def on_close(self):
        """Handle window close event."""
        # Check if bot is running
        if self.bot_process and self.bot_process.poll() is None:
            if not messagebox.askyesno("Bot Running", 
                                      "Bot is still running. Close GUI anyway?\n\n"
                                      "(Bot will continue running in background)"):
                return
        
        # Check for unsaved changes
        if self.config_changed:
            result = messagebox.askyesnocancel("Unsaved Changes", 
                                               "You have unsaved changes. Save before closing?")
            if result is None:  # Cancel
                return
            elif result:  # Yes
                self.save_configuration()
        
        self.root.destroy()
        
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


def main():
    """Entry point."""
    app = BotLauncherGUI()
    app.run()


if __name__ == "__main__":
    main()
