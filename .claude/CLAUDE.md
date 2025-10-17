# Home Assistant TUI Project

Terminal UI for controlling Home Assistant via WebSocket API with vim-style navigation.

## Project Structure

```
src/hass_tui/
├── websocket_client.py  # Educational WebSocket client with detailed comments
├── hass_api.py          # Home Assistant API wrapper
├── config.py            # YAML config loader with hierarchy support
├── app.py               # Main Textual TUI with vim navigation
└── main.py              # Entry point

config.yaml              # Project defaults (version controlled)
~/.config/hass_tui/
└── config.yaml          # User overrides (favorites, keybindings)
```

## Tech Stack

- Python 3.11+
- Textual (TUI framework)
- websockets (WebSocket client)
- pydantic (config validation)
- PyYAML (config files)

## Setup

```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Installation

```bash
# Setup creates symlink to ~/.applications/bin/hass
# Ensure ~/.applications/bin is in your PATH
./hass  # Test it works locally first
```

Add to PATH if needed:
```bash
export PATH="$HOME/.applications/bin:$PATH"  # Add to ~/.bashrc or ~/.zshrc
```

## Run

```bash
# From anywhere (after installation)
hass

# Or directly from project directory
python run.py
```

## Testing

**IMPORTANT**: Never run the TUI app directly via automated tools/scripts as it will corrupt the terminal.

```bash
# Run tests safely (headless mode)
pytest

# Run specific test
pytest tests/test_app.py -v
```

Tests use Textual's `run_test()` mode which runs headless without terminal escape sequences.

## Key Features

- **Vim Navigation**: hjkl, gg, G, /, n, N
- **Command Mode**: `:` prefix (`:fav`, `:search`, `:group`, `:quit`)
- **Favorites**: Press `f` to toggle, shown first with ★ marker
- **Context Menu**: Spacebar for quick device controls
- **Filter Tabs**: All, Favorites, Lights, Climate, Switches with counts
- **Grouping**: favorites_first, type, room, state
- **Real-time Updates**: WebSocket-based live state changes
- **YAML Config**: Project defaults + user overrides

## Keybindings

### Navigation
- `j`/`k`: Down/Up
- `h`/`l`: Left/Right (select)
- `gg`: Jump to top
- `G`: Jump to bottom
- `/`: Search
- `n`/`N`: Next/previous match

### Actions
- `f`: Toggle favorite
- `space`: Context menu
- `:`: Command mode
- `r`: Refresh
- `c`: Reconnect
- `q`: Quit

### Commands
- `:fav` - Show favorites only
- `:all` - Show all entities
- `:lights` / `:climate` / `:switches` - Filter by type
- `:search <term>` - Search entities
- `:group type|room|state|favorites_first` - Change grouping
- `:quit` - Exit app

## Configuration

Config hierarchy (later overrides earlier):
1. `./config.yaml` - Project defaults
2. `~/.config/hass_tui/config.yaml` - User overrides

See `config.yaml` for customizable options (keybindings, filters, defaults).

## Development Notes

**For AI Assistants**:
- NEVER run `python run.py` or launch the TUI app via Bash commands - it will corrupt the terminal
- Only work with code (read, edit, analyze)
- Use pytest for testing - tests run in headless mode
- Let the user run the app in their own terminal

## Recent Changes

**Latest** - Security review and fixes for public release
- Fixed hardcoded personal path in `hass` wrapper script (now uses dynamic path resolution)
- Updated README.md GitHub clone URL from placeholder to actual username (HamYam)
- Verified no credentials, tokens, or sensitive data in git history
- Confirmed .env files properly ignored and never committed

**Previous** - Added GitHub documentation
- Created comprehensive README.md with features, installation, usage, and keybindings
- Added MIT LICENSE file (copyright HamYam)
- README includes all key features, entity types supported, and development guide

**Previous** - Fixed wrapper script paths
- Fixed `hass` wrapper to use absolute project path instead of script directory
- Wrapper now correctly finds venv and run.py in project location
- Works properly when symlinked from ~/.applications/bin/hass

**Previous** - PATH-accessible executable wrapper
- Created `hass` bash wrapper script that activates venv and runs app
- Symlinked to `~/.applications/bin/hass` for system-wide access
- Can now run `hass` from anywhere instead of `python run.py`
- Wrapper uses absolute paths to project directory

**Previous** - Real-time search filtering
- Search now filters entities as you type (live updates on each keystroke)
- Added `SearchUpdated` message for live search updates
- Added `on_input_changed` handler to CommandLine component
- Pressing `/` and typing immediately filters the entity list
- Pressing Enter still shows result notification, Escape clears search

**Previous** - Fixed command line and search keybindings with visual improvements
- Fixed `:` and `/` keybindings which weren't working due to invalid key names
- Implemented `on_key()` handler to properly catch colon and slash keypresses
- Command mode (`:`) and search mode (`/`) now fully functional
- Color-coded prefixes: cyan `:` for command mode, yellow `/` for search mode
- Improved placeholder text with helpful hints
- Fixed command line visibility (increased height, added overlay layer)
- Command line now clearly visible at bottom of screen

**Previous** - Testing infrastructure and terminal safety
- Added pytest configuration with async support
- Created test structure using Textual's headless test mode
- Added pytest and pytest-asyncio to requirements
- Documented terminal corruption issue and safe testing practices

**Latest** - Rich entity-specific visualizations
- Replaced generic details panel with type-specific visualizations inspired by Home Assistant cards
- Climate entities: Show current/target temps with color-coded heating/cooling status (🔥/❄️), HVAC modes, humidity, and visual activity bars
- Light entities: Display on/off status, brightness bars, color temperature (warm/cool indicators), RGB colors
- Switch entities: Large status indicators with power consumption and device class
- Generic fallback: Improved attribute display with formatting for unknown entity types
- Removed redundant control panel (controls accessible via spacebar context menu)
- Updated CSS with better spacing and visual hierarchy for visualization panel

**Previous** - Auto-display entity details on cursor movement
- Details panel automatically updates when navigating with j/k
- No need to press Enter or 'l' to select entity for viewing details
- First entity in list auto-displays when table updates
- Cursor movement (j/k/gg/G) immediately shows highlighted entity info

**Previous** - Context menu fixes and improvements
- Fixed context menu dialog being broken (proper error handling and button activation)
- Changed hotkeys from numbers to letters (e.g., [O]n, O[f]f, [T]oggle)
- Hotkey letters shown in brackets within button text (no extra field)
- Input fields pre-populate with current values (e.g., temperature)
- Temperature can be set directly from context menu with Enter or hotkey
- Reduced context menu spacing for compact UI

**Previous** - Bug fixes and UX improvements
- Fixed DataTable duplicate row key crash (app.py:627) by using entity_id as unique key
- Optimized state update from O(n) to O(1) using direct key lookup (app.py:940-943)
- Fixed NoActiveWorker crash in context menu (app.py:836) using push_screen callback pattern
- Context menu now works on highlighted row (j/k navigation) instead of requiring selection
- Prevents crashes during high-frequency WebSocket state change events (100+/min)

**Commit c7c1138** - Vim navigation, command mode, favorites
- Added vim-style hjkl navigation + gg/G/n/N
- Implemented `:` command mode (search, filter, group)
- Added favorites system with ★ markers and persistent storage
- Created spacebar context menu with quick controls
- Added filter bar with entity counts
- Implemented grouping/sorting (favorites-first, type, room, state)
- YAML config hierarchy (project + user overrides)
- Support for configurable keybindings and entity filters

**Commit 78321b5** - Initial implementation
- Created educational WebSocket client (400+ lines of comments)
- Built Textual TUI with real-time updates
- Implemented light and climate controls
- Added event subscription for live state changes
