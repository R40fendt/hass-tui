"""Configuration management for Home Assistant TUI."""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class DisplayConfig(BaseModel):
    """Display settings."""
    default_group: str = "favorites_first"  # favorites_first, type, room, state
    default_filter: str = "all"  # all, favorites, lights, climate, etc.
    show_counts: bool = True


class FiltersConfig(BaseModel):
    """Entity filter settings."""
    domains: List[str] = ["light", "climate", "switch", "fan", "cover", "media_player"]


class KeybindingsConfig(BaseModel):
    """Keybinding settings."""
    navigate_down: str = "j"
    navigate_up: str = "k"
    navigate_left: str = "h"
    navigate_right: str = "l"
    navigate_select: str = "l"
    jump_top: str = "g g"
    jump_bottom: str = "G"
    search: str = "/"
    search_next: str = "n"
    search_prev: str = "N"
    toggle_favorite: str = "f"
    context_menu: str = "space"
    command_mode: str = ":"
    refresh: str = "r"
    reconnect: str = "c"
    quit: str = "q"


class AppConfig(BaseModel):
    """Application configuration (from YAML)."""
    favorites: List[str] = []
    display: DisplayConfig = DisplayConfig()
    filters: FiltersConfig = FiltersConfig()
    keybindings: KeybindingsConfig = KeybindingsConfig()


class Config(BaseModel):
    """Full application configuration."""

    # Home Assistant connection (from .env)
    hass_url: str = Field(..., description="Home Assistant URL")
    hass_token: str = Field(..., description="Home Assistant access token")

    # App settings (from YAML)
    app: AppConfig = AppConfig()

    @field_validator("hass_url")
    @classmethod
    def convert_to_ws(cls, v: str) -> str:
        """Convert HTTP URL to WebSocket URL."""
        # Replace http:// or https:// with ws:// or wss://
        if v.startswith("http://"):
            v = v.replace("http://", "ws://", 1)
        elif v.startswith("https://"):
            v = v.replace("https://", "wss://", 1)

        # Ensure it ends with the WebSocket API path
        if not v.endswith("/api/websocket"):
            v = v.rstrip("/") + "/api/websocket"

        return v


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    Override values take precedence over base values.
    Nested dictionaries are merged recursively.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_yaml_config() -> AppConfig:
    """
    Load YAML configuration with hierarchy.

    Config hierarchy (later overrides earlier):
    1. Project defaults: ./config.yaml
    2. User overrides: ~/.config/hass_tui/config.yaml

    Returns:
        AppConfig object with merged configuration
    """
    # Project root
    project_root = Path(__file__).parent.parent.parent
    project_config_path = project_root / "config.yaml"

    # User config directory
    user_config_dir = Path.home() / ".config" / "hass_tui"
    user_config_path = user_config_dir / "config.yaml"

    # Start with empty config
    merged_config: Dict[str, Any] = {}

    # Load project defaults
    if project_config_path.exists():
        with open(project_config_path, "r") as f:
            project_config = yaml.safe_load(f) or {}
            merged_config = deep_merge(merged_config, project_config)

    # Load user overrides
    if user_config_path.exists():
        with open(user_config_path, "r") as f:
            user_config = yaml.safe_load(f) or {}
            merged_config = deep_merge(merged_config, user_config)

    # Parse into Pydantic model
    return AppConfig(**merged_config)


def save_user_config(app_config: AppConfig) -> None:
    """
    Save user configuration to ~/.config/hass_tui/config.yaml

    Args:
        app_config: AppConfig to save
    """
    user_config_dir = Path.home() / ".config" / "hass_tui"
    user_config_path = user_config_dir / "config.yaml"

    # Create directory if it doesn't exist
    user_config_dir.mkdir(parents=True, exist_ok=True)

    # Convert to dict and save
    config_dict = app_config.model_dump()

    with open(user_config_path, "w") as f:
        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)


def load_config(env_file: Optional[str] = None) -> Config:
    """
    Load full configuration from environment and YAML files.

    Args:
        env_file: Path to .env file (defaults to .env.prod)

    Returns:
        Config object with connection and app settings
    """
    if env_file is None:
        # Look for .env.prod in project root
        env_file = Path(__file__).parent.parent.parent / ".env.prod"

    if not Path(env_file).exists():
        raise FileNotFoundError(f"Config file not found: {env_file}")

    load_dotenv(env_file)

    # Load app config from YAML
    app_config = load_yaml_config()

    return Config(
        hass_url=os.getenv("HASS_URL"),
        hass_token=os.getenv("HASS_TOKEN"),
        app=app_config
    )
