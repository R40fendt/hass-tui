# Home Assistant TUI

Terminal UI for controlling Home Assistant with vim-style navigation and real-time updates.

## Features

- **Vim Navigation**: hjkl, gg, G, /, n, N for quick movement
- **Command Mode**: `:` prefix for filtering and grouping (`:lights`, `:fav`, `:group type`)
- **Favorites**: Press `f` to toggle, shown first with ★ marker
- **Context Menu**: Spacebar for quick device controls
- **Filter Tabs**: All, Favorites, Lights, Climate, Switches with live counts
- **Real-time Updates**: WebSocket-based live state changes
- **Rich Visualizations**: Entity-specific cards inspired by Home Assistant UI
- **YAML Config**: Project defaults + user overrides

## Requirements

- Python 3.11+
- Home Assistant instance with WebSocket API enabled
- Terminal with 256 color support

## Installation

```bash
# Clone the repository
git clone https://github.com/HamYam/hass_tui.git
cd hass_tui

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your Home Assistant URL and token

# Optional: Install system-wide
./hass  # Creates symlink to ~/.applications/bin/hass
```

Add `~/.applications/bin` to your PATH:
```bash
echo 'export PATH="$HOME/.applications/bin:$PATH"' >> ~/.bashrc
```

## Usage

```bash
# From anywhere (after installation)
hass

# Or from project directory
python run.py
```

## Configuration

Config hierarchy (later overrides earlier):
1. `./config.yaml` - Project defaults
2. `~/.config/hass_tui/config.yaml` - User overrides

Example user config (`~/.config/hass_tui/config.yaml`):
```yaml
favorites:
  - light.living_room
  - climate.bedroom

display:
  default_group: type
  default_filter: favorites

filters:
  domains:
    - light
    - climate
    - switch
```

## Keybindings

### Navigation
- `j`/`k` - Down/Up
- `h`/`l` - Left/Right
- `gg` - Jump to top
- `G` - Jump to bottom
- `/` - Search (live filtering)
- `n`/`N` - Next/previous match

### Actions
- `f` - Toggle favorite
- `space` - Context menu
- `:` - Command mode
- `r` - Refresh
- `c` - Reconnect
- `q` - Quit

### Commands
- `:fav` - Show favorites only
- `:all` - Show all entities
- `:lights` / `:climate` / `:switches` - Filter by type
- `:search <term>` - Search entities
- `:group type|room|state|favorites_first` - Change grouping
- `:quit` - Exit app

## Entity Types Supported

- **Lights**: Brightness, color temperature, RGB colors
- **Climate**: Temperature control, HVAC modes, humidity
- **Switches**: On/off, power consumption
- **Fans**: Speed control
- **Covers**: Open/close, position
- **Media Players**: Play/pause, volume

## Development

```bash
# Run tests (headless mode)
pytest

# Run specific test
pytest tests/test_app.py -v

# Validate config
python validate_config.py
```

**Note**: Never run the TUI app via automated scripts - it will corrupt the terminal. Use pytest for testing.

## Tech Stack

- [Textual](https://textual.textualize.io/) - Modern TUI framework
- [websockets](https://websockets.readthedocs.io/) - WebSocket client
- [Pydantic](https://docs.pydantic.dev/) - Config validation
- [PyYAML](https://pyyaml.org/) - YAML parsing

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.
