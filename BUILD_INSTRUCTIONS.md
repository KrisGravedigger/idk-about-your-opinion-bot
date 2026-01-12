# Build Instructions for Opinion Trading Bot

This guide explains how to build standalone executables for the Opinion Trading Bot using PyInstaller.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Local Build (Testing)](#local-build-testing)
- [Creating a Release (GitHub Actions)](#creating-a-release-github-actions)
- [Build System Architecture](#build-system-architecture)
- [Troubleshooting](#troubleshooting)
- [Distribution](#distribution)

---

## Overview

The Opinion Trading Bot uses **PyInstaller** to create standalone executables for Windows, Linux, and macOS. This allows non-technical users to run the bot without installing Python or managing dependencies.

**Build Methods:**

1. **Local Build** - For testing and development
2. **GitHub Actions** - Automated multi-platform builds for releases

---

## Prerequisites

### For Local Builds

- Python 3.10 or higher
- All dependencies from `requirements.txt`
- PyInstaller 5.0+

```bash
# Install dependencies
pip install -r requirements.txt

# Install PyInstaller
pip install pyinstaller
```

### For GitHub Actions Builds

- GitHub repository with the bot code
- Git installed locally
- Permission to push tags to the repository

---

## Local Build (Testing)

Use local builds to test the executable before creating a release.

### Step 1: Install Build Dependencies

```bash
# Install all dependencies including PyInstaller
pip install -r requirements.txt
pip install pyinstaller packaging
```

### Step 2: Run PyInstaller

```bash
# Build using the spec file
pyinstaller build_gui.spec
```

**What this does:**
- Analyzes `gui_launcher.py` and all imported modules
- Bundles Python interpreter and dependencies
- Creates one-folder distribution in `dist/OpinionBot/`
- Includes data files (.env.example, README.md, version.txt)

### Step 3: Test the Build

```bash
# Navigate to build output
cd dist/OpinionBot

# Run the executable
./OpinionBot        # Linux/macOS
OpinionBot.exe      # Windows
```

**First-Run Testing:**
1. Delete any existing .env, state.json, bot_config.json
2. Run the executable
3. Verify welcome wizard appears
4. Verify .env and bot_config.json are created
5. Test configuration and bot startup

### Step 4: Clean Build (if needed)

```bash
# Remove previous build artifacts
rm -rf build/ dist/

# Rebuild
pyinstaller build_gui.spec
```

---

## Creating a Release (GitHub Actions)

GitHub Actions automatically builds executables for all platforms when you push a version tag.

### Step 1: Update Version Number

Edit `version.txt`:
```
0.4.0
```

### Step 2: Commit Changes

```bash
git add version.txt
git commit -m "Bump version to 0.4.0"
git push origin main
```

### Step 3: Create and Push Tag

```bash
# Create tag (must start with 'v')
git tag v0.4.0

# Push tag to GitHub
git push origin v0.4.0
```

**What happens next:**
1. GitHub Actions detects the tag push
2. Builds start on 3 runners (Windows, Linux, macOS)
3. Each runner:
   - Installs Python 3.10
   - Installs dependencies
   - Runs PyInstaller
   - Creates version.txt with tag version
   - Copies additional files
   - Creates ZIP archive
4. All ZIPs are uploaded to GitHub Releases
5. Release is published automatically (~10-15 minutes)

### Step 4: Verify Release

Visit: `https://github.com/YOUR_USERNAME/idk-about-your-opinion-bot/releases`

You should see:
- Release titled `v0.4.0`
- 3 download links:
  - `OpinionBot_Windows.zip`
  - `OpinionBot_Linux.zip`
  - `OpinionBot_macOS.zip`

### Step 5: Test Downloads

Download and test each platform's ZIP:
1. Extract to new folder
2. Run executable
3. Verify first-run setup works
4. Verify update checker works
5. Test basic bot functionality

---

## Build System Architecture

### Files Involved

```
opinion_trading_bot/
├── build_gui.spec              # PyInstaller specification
├── version.txt                 # Current version (0.3.0)
├── RELEASE_README.txt          # User documentation for releases
├── BUILD_INSTRUCTIONS.md       # This file
├── .github/
│   └── workflows/
│       └── build-release.yml   # GitHub Actions workflow
└── gui_launcher.py             # Entry point (with update checker)
```

### PyInstaller Configuration

**`build_gui.spec` includes:**

1. **Entry Point**: `gui_launcher.py`
2. **Data Files**:
   - `.env.example` - Template
   - `README.md` - Documentation
   - `version.txt` - Version info
3. **Hidden Imports**:
   - `opinion_clob_sdk` and submodules
   - `web3`, `requests`, `dotenv`
   - All bot modules
4. **Exclusions**:
   - `tests/` directory
   - `docs/` directory
   - Test frameworks (pytest, unittest)
5. **Build Mode**: One-folder (easier for updates)
6. **Console**: False (GUI application)

### Distribution Structure

```
OpinionBot/
├── OpinionBot.exe              # Main executable (Windows)
├── _internal/                  # Dependencies (auto-generated)
│   ├── Python DLLs
│   ├── Library files
│   └── Compiled modules
├── .env.example               # Credentials template
├── README.md                  # Full documentation
├── README_RELEASE.txt         # Quick start guide
└── version.txt                # Version (0.3.0)
```

**User Files (NOT included):**
- `.env` - Created on first run
- `bot_config.json` - Created on first run
- `state.json` - Created by bot
- `pnl_stats.json` - Created by bot
- `bonus_markets.txt` - Created on first run
- `opinion_farming_bot.log` - Created by bot

---

## Troubleshooting

### PyInstaller Errors

**"ModuleNotFoundError" during build:**
- Add missing module to `hiddenimports` in `build_gui.spec`
- Common culprits: SDK submodules, web3 providers

```python
hiddenimports=[
    'opinion_clob_sdk.missing_module',
    'web3.providers.missing_provider',
]
```

**"FileNotFoundError" for data files:**
- Verify file exists before running PyInstaller
- Check path in `datas` list in `build_gui.spec`

```python
datas=[
    ('path/to/file', 'destination/'),
]
```

**Build succeeds but executable crashes:**
- Run with `--debug all` flag to see detailed errors
- Check `opinion_farming_bot.log` in dist folder
- Test in clean environment

```bash
pyinstaller --debug all build_gui.spec
cd dist/OpinionBot
./OpinionBot
```

### GitHub Actions Errors

**Build fails on specific platform:**
- Check workflow logs in Actions tab
- Common issues:
  - Platform-specific dependencies
  - Path separators (use `/` or `os.path.join`)
  - Missing files on that platform

**Release not created:**
- Verify tag starts with `v` (e.g., `v0.4.0`)
- Check `GITHUB_TOKEN` has release permissions
- Check workflow `if:` conditions

**ZIP not uploaded:**
- Check artifact creation step succeeded
- Verify ZIP file was created
- Check upload step logs

### Runtime Errors

**"Failed to execute script" on startup:**
- Missing hidden import
- Data file not bundled
- Check logs: `opinion_farming_bot.log`

**Update checker not working:**
- Verify `version.txt` exists in build
- Check GitHub API URL in `gui_launcher.py`
- Verify internet connection

**First-run setup not triggered:**
- Check `check_first_run_and_setup()` is called in `__init__`
- Verify `.env.example` is bundled
- Check file creation logic

---

## Distribution

### Creating Distributable Package

After building, create a user-friendly package:

1. **Test the build thoroughly**
   ```bash
   cd dist/OpinionBot
   ./OpinionBot  # or OpinionBot.exe
   ```

2. **Add release documentation**
   ```bash
   cp RELEASE_README.txt dist/OpinionBot/README_RELEASE.txt
   ```

3. **Create ZIP manually (if needed)**
   ```bash
   cd dist
   zip -r OpinionBot_Linux.zip OpinionBot/     # Linux/macOS
   # or
   powershell Compress-Archive -Path OpinionBot -DestinationPath OpinionBot_Windows.zip  # Windows
   ```

4. **Test ZIP extraction**
   - Extract to new location
   - Verify all files present
   - Run executable

### File Size Expectations

| Platform | Compressed (ZIP) | Extracted |
|----------|------------------|-----------|
| Windows  | 40-60 MB         | 120-150 MB |
| Linux    | 35-50 MB         | 100-130 MB |
| macOS    | 40-55 MB         | 110-140 MB |

Large size is normal - includes Python interpreter and all dependencies.

### Updating Users

When releasing a new version:

1. **Update `version.txt`** - New version number
2. **Update `README.md`** - Changelog in "What's New" section
3. **Create tag and push** - GitHub Actions builds automatically
4. **Test all platforms** - Download and verify
5. **Announce update** - Users will be notified via update checker

**Update Process for Users:**
1. Bot notifies of new version (automatic)
2. User downloads new ZIP
3. Extracts to **same folder** (overwrites executables)
4. User files preserved (.env, state.json, etc.)
5. Bot starts with new version

---

## Advanced Topics

### Customizing the Build

**Change executable icon:**
1. Create `icon.ico` (Windows) or `icon.icns` (macOS)
2. Place in project root
3. `build_gui.spec` auto-detects and uses it

**Add custom data files:**
```python
# In build_gui.spec
datas=[
    ('path/to/custom_file.txt', '.'),
    ('path/to/folder/', 'folder_name/'),
]
```

**Reduce executable size:**
1. Use `--exclude-module` for unused libraries
2. Disable UPX compression if issues occur
3. Strip debug symbols (already enabled)

### Code Signing

**For production releases**, consider code signing:

**Windows:**
- Use `signtool.exe` with code signing certificate
- Prevents SmartScreen warnings

**macOS:**
- Use `codesign` with Apple Developer ID
- Notarize with Apple for Gatekeeper approval

**Not required for:**
- Open source projects
- Testing
- Internal use

### Debugging Build Issues

**Enable verbose logging:**
```bash
pyinstaller --log-level DEBUG build_gui.spec
```

**Check import resolution:**
```bash
pyi-archive_viewer dist/OpinionBot/OpinionBot.exe  # Windows
pyi-archive_viewer dist/OpinionBot/OpinionBot      # Linux/macOS
```

**Test in minimal environment:**
```bash
# Create clean virtual environment
python -m venv test_env
source test_env/bin/activate  # Linux/macOS
# or
test_env\Scripts\activate  # Windows

# Install only runtime deps
pip install -r requirements.txt
```

---

## Next Steps

After building:

1. **Test thoroughly** - All platforms, all features
2. **Document changes** - Update README.md changelog
3. **Create release** - Push tag, wait for GitHub Actions
4. **Verify release** - Download and test all ZIPs
5. **Announce** - Users will receive update notification

For questions or issues with the build system:
- Check PyInstaller docs: https://pyinstaller.org/
- GitHub Actions docs: https://docs.github.com/en/actions
- Open issue: https://github.com/YOUR_USERNAME/idk-about-your-opinion-bot/issues

---

**Happy Building! 🔨**
