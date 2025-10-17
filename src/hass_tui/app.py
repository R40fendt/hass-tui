"""
Home Assistant TUI Application

Built with Textual, a modern Python TUI framework.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Set
from enum import Enum

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Static, Input, Button, DataTable, Label
from textual.binding import Binding
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.message import Message

from .websocket_client import HomeAssistantWebSocket, ConnectionState
from .hass_api import HomeAssistantAPI
from .config import load_config, save_user_config


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class GroupMode(str, Enum):
    """Entity grouping modes."""
    FAVORITES_FIRST = "favorites_first"
    TYPE = "type"
    ROOM = "room"
    STATE = "state"


class FilterMode(str, Enum):
    """Entity filter modes."""
    ALL = "all"
    FAVORITES = "favorites"
    LIGHTS = "lights"
    CLIMATE = "climate"
    SWITCHES = "switches"


class CommandLine(Container):
    """Vim-style command line that appears at the bottom."""

    class CommandSubmitted(Message):
        """Message sent when command is submitted."""
        def __init__(self, command: str, mode: str) -> None:
            self.command = command
            self.mode = mode  # "command" or "search"
            super().__init__()

    class SearchUpdated(Message):
        """Message sent when search text changes (live filtering)."""
        def __init__(self, search_term: str) -> None:
            self.search_term = search_term
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = "command"  # "command" or "search"

    def compose(self) -> ComposeResult:
        """Compose command line with prefix and input."""
        yield Label(":", id="cmd-prefix")
        yield Input(placeholder="", id="cmd-input")

    def show(self, mode: str = "command") -> None:
        """Show command line in specified mode."""
        self.mode = mode
        prefix = self.query_one("#cmd-prefix", Label)
        cmd_input = self.query_one("#cmd-input", Input)

        if mode == "search":
            prefix.update("[yellow]/[/]")
            cmd_input.placeholder = "search entities..."
        else:
            prefix.update("[cyan]:[/]")
            cmd_input.placeholder = "enter command (fav, all, lights, climate, quit)..."

        self.display = True
        cmd_input.value = ""
        cmd_input.focus()

    def hide(self) -> None:
        """Hide command line and return focus."""
        self.display = False
        cmd_input = self.query_one("#cmd-input", Input)
        cmd_input.value = ""
        self.app.query_one(EntityList).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in command input."""
        if event.input.id == "cmd-input":
            command = event.value.strip()
            if command:
                self.post_message(self.CommandSubmitted(command, self.mode))
            self.hide()
            event.stop()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for live search filtering."""
        if event.input.id == "cmd-input" and self.mode == "search":
            # Post live search update message
            self.post_message(self.SearchUpdated(event.value))
            event.stop()

    async def on_key(self, event) -> None:
        """Handle key presses in command line."""
        if event.key == "escape":
            self.hide()
            event.prevent_default()
            event.stop()


class FilterBar(Static):
    """Tab/filter bar showing entity counts and active filter."""

    current_filter = reactive("all")
    counts = reactive({})

    def render(self) -> str:
        """Render filter bar with counts."""
        if not self.counts:
            return "[dim]Loading...[/]"

        all_count = self.counts.get("all", 0)
        fav_count = self.counts.get("favorites", 0)
        light_count = self.counts.get("lights", 0)
        climate_count = self.counts.get("climate", 0)
        switch_count = self.counts.get("switches", 0)

        # Highlight active filter
        def fmt(name: str, count: int) -> str:
            display_name = name.capitalize()
            if self.current_filter == name:
                return f"[black on white] {display_name}: {count} [/]"
            else:
                return f"[dim]{display_name}:[/] {count}"

        return " | ".join([
            fmt("all", all_count),
            fmt("favorites", fav_count),
            fmt("lights", light_count),
            fmt("climate", climate_count),
            fmt("switches", switch_count),
        ])


class TemperatureInputDialog(ModalScreen):
    """Simple dialog for temperature input."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current_temp: str = "", **kwargs):
        super().__init__(**kwargs)
        self.current_temp = current_temp

    def compose(self) -> ComposeResult:
        """Compose temperature input dialog."""
        with Container(id="temp-dialog-container"):
            yield Label("[bold]Set Temperature[/]", id="temp-dialog-title")
            yield Input(value=self.current_temp, placeholder="Temperature", id="temp-dialog-input")
            with Horizontal(id="temp-dialog-buttons"):
                yield Button("Set", id="temp-dialog-set", variant="primary")
                yield Button("Cancel", id="temp-dialog-cancel")

    def on_mount(self) -> None:
        """Focus input when mounted."""
        self.query_one("#temp-dialog-input", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "temp-dialog-set":
            temp_input = self.query_one("#temp-dialog-input", Input)
            self.dismiss(temp_input.value)
        else:
            self.dismiss(None)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(None)


class ContextMenu(ModalScreen):
    """Context menu for entity actions (spacebar) with letter hotkey support."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("f", "hotkey_f", "Favorite", show=False),
        Binding("r", "hotkey_r", "Remove", show=False),
        Binding("o", "hotkey_o", "On", show=False),
        Binding("x", "hotkey_x", "Off", show=False),
        Binding("t", "hotkey_t", "Toggle", show=False),
        Binding("s", "hotkey_s", "Set", show=False),
        Binding("h", "hotkey_h", "Heat", show=False),
        Binding("c", "hotkey_c", "Cool", show=False),
        Binding("enter", "activate", "Select", show=False),
    ]

    def __init__(self, entity: Dict[str, Any], is_favorite: bool, **kwargs):
        super().__init__(**kwargs)
        self.entity = entity
        self.is_favorite = is_favorite
        self.action_map = {}  # Maps hotkey letter to action_id

    def compose(self) -> ComposeResult:
        """Compose context menu with letter hotkeys."""
        entity_id = self.entity.get("entity_id", "Unknown")
        domain = entity_id.split(".")[0]

        with Container(id="context-menu-container"):
            yield Label(f"[bold]{entity_id}[/]", id="context-menu-title")

            with VerticalScroll(id="context-menu-items"):
                # Domain-specific controls
                if domain == "light":
                    self.action_map["o"] = "ctx-light-on"
                    yield Button("💡 [underline]O[/]n", id="ctx-light-on", variant="success")

                    self.action_map["x"] = "ctx-light-off"
                    yield Button("💡 O[underline]f[/]f", id="ctx-light-off", variant="error")

                    self.action_map["t"] = "ctx-light-toggle"
                    yield Button("🔄 [underline]T[/]oggle", id="ctx-light-toggle")

                elif domain == "climate":
                    self.action_map["s"] = "ctx-set-temp"
                    yield Button("🌡️ [underline]S[/]et Temp", id="ctx-set-temp", variant="primary")

                    self.action_map["h"] = "ctx-hvac-heat"
                    yield Button("🔥 [underline]H[/]eat", id="ctx-hvac-heat")

                    self.action_map["c"] = "ctx-hvac-cool"
                    yield Button("❄️ [underline]C[/]ool", id="ctx-hvac-cool")

                    self.action_map["x"] = "ctx-hvac-off"
                    yield Button("⭕ O[underline]f[/]f", id="ctx-hvac-off")

                elif domain == "switch":
                    self.action_map["o"] = "ctx-switch-on"
                    yield Button("⚡ [underline]O[/]n", id="ctx-switch-on", variant="success")

                    self.action_map["x"] = "ctx-switch-off"
                    yield Button("⚡ O[underline]f[/]f", id="ctx-switch-off", variant="error")

                    self.action_map["t"] = "ctx-switch-toggle"
                    yield Button("🔄 [underline]T[/]oggle", id="ctx-switch-toggle")

                # Favorite toggle at bottom
                fav_label = "[underline]R[/]emove from Favorites" if self.is_favorite else "[underline]F[/]avorite"
                self.action_map["f" if not self.is_favorite else "r"] = "ctx-toggle-fav"
                yield Button(f"★ {fav_label}", id="ctx-toggle-fav", variant="primary")

    def action_move_down(self) -> None:
        """Move focus down."""
        self.focus_next()

    def action_move_up(self) -> None:
        """Move focus previous."""
        self.focus_previous()

    def action_activate(self) -> None:
        """Activate focused button (Enter key)."""
        focused = self.focused
        if isinstance(focused, Button):
            button_id = focused.id
            # Trigger button press to handle special cases like set-temp
            focused.press()

    def _handle_hotkey(self, letter: str) -> None:
        """Handle letter hotkey press."""
        if letter in self.action_map:
            action_id = self.action_map[letter]
            # Special handling for set-temp - open input dialog
            if action_id == "ctx-set-temp":
                current_temp = self.entity.get("attributes", {}).get("temperature", "")
                temp_value = str(current_temp) if current_temp else ""

                def handle_temp_result(result):
                    if result:
                        self.dismiss(("ctx-set-temp", result))
                    # If cancelled (None), just stay in context menu

                self.app.push_screen(TemperatureInputDialog(temp_value), callback=handle_temp_result)
            else:
                self.dismiss(action_id)

    def action_hotkey_f(self) -> None:
        self._handle_hotkey("f")

    def action_hotkey_r(self) -> None:
        self._handle_hotkey("r")

    def action_hotkey_o(self) -> None:
        self._handle_hotkey("o")

    def action_hotkey_x(self) -> None:
        self._handle_hotkey("x")

    def action_hotkey_t(self) -> None:
        self._handle_hotkey("t")

    def action_hotkey_s(self) -> None:
        self._handle_hotkey("s")

    def action_hotkey_h(self) -> None:
        self._handle_hotkey("h")

    def action_hotkey_c(self) -> None:
        self._handle_hotkey("c")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        # Special handling for set-temp button - open input dialog
        if button_id == "ctx-set-temp":
            current_temp = self.entity.get("attributes", {}).get("temperature", "")
            temp_value = str(current_temp) if current_temp else ""

            def handle_temp_result(result):
                if result:
                    self.dismiss(("ctx-set-temp", result))
                # If cancelled (None), just stay in context menu

            self.app.push_screen(TemperatureInputDialog(temp_value), callback=handle_temp_result)
        else:
            self.dismiss(button_id)


class ConnectionStatus(Static):
    """Displays WebSocket connection status."""

    status = reactive("Disconnected")

    def render(self) -> str:
        """Render connection status."""
        status_colors = {
            "Connected": "[green]",
            "Connecting": "[yellow]",
            "Authenticating": "[yellow]",
            "Disconnected": "[red]",
            "Reconnecting": "[yellow]",
        }
        color = status_colors.get(self.status, "[white]")
        return f"{color}{self.status}[/] | Home Assistant TUI"


class EntityList(DataTable):
    """
    Table displaying Home Assistant entities.

    Shows entity ID, state, and domain (light, climate, etc.)
    Supports vim-style navigation.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cursor_type = "row"
        self.search_term: str = ""
        self.search_matches: List[int] = []
        self.search_index: int = 0
        self.last_key: str = ""  # For handling 'gg' double key press

    def on_mount(self):
        """Set up table columns."""
        self.add_columns("Fav", "Entity ID", "State", "Type")


class EntityVisualization(Static):
    """Rich, entity-type-specific visualization panel."""

    entity = reactive(None)

    def render(self) -> str:
        """Render entity with type-specific visualization."""
        if not self.entity:
            return "[dim]Select an entity to view details[/]"

        entity_id = self.entity.get("entity_id", "Unknown")
        domain = entity_id.split(".")[0]

        # Route to type-specific renderer
        if domain == "climate":
            return self._render_climate()
        elif domain == "light":
            return self._render_light()
        elif domain == "switch":
            return self._render_switch()
        else:
            return self._render_generic()

    def _render_climate(self) -> str:
        """Render climate entity with thermostat-style visualization."""
        entity_id = self.entity.get("entity_id", "Unknown")
        state = self.entity.get("state", "off")
        attrs = self.entity.get("attributes", {})

        # Temperature values
        current_temp = attrs.get("current_temperature", "—")
        target_temp = attrs.get("temperature", "—")
        temp_unit = attrs.get("unit_of_measurement", "°C")

        # HVAC status and mode
        hvac_action = attrs.get("hvac_action", state)
        hvac_mode = attrs.get("hvac_mode", state)

        # Additional stats
        humidity = attrs.get("current_humidity", None)
        power = attrs.get("power", None)

        # Color code based on HVAC action
        if hvac_action == "heating":
            status_color = "red"
            status_icon = "🔥"
            status_text = "HEATING"
        elif hvac_action == "cooling":
            status_color = "blue"
            status_icon = "❄️"
            status_text = "COOLING"
        elif hvac_action == "idle" or state == "on":
            status_color = "yellow"
            status_icon = "⚡"
            status_text = "IDLE"
        else:
            status_color = "dim"
            status_icon = "⭕"
            status_text = "OFF"

        # Build visualization
        lines = [
            f"[bold]{entity_id}[/]",
            "",
            f"[bold white]Current:[/] [{status_color}]{current_temp}{temp_unit}[/]  [{status_color}]{status_icon} {status_text}[/]",
            f"[bold white]Target:[/]  [cyan]{target_temp}{temp_unit}[/]",
            "",
        ]

        # Mode display
        modes = attrs.get("hvac_modes", [])
        if modes:
            mode_str = " | ".join(modes)
            lines.append(f"[dim]Modes:[/] {mode_str}")

        # Additional stats
        if humidity is not None:
            lines.append(f"[dim]Humidity:[/] {humidity}%")
        if power is not None:
            lines.append(f"[dim]Power:[/] {power}")

        # Activity indicator (visual bar)
        if hvac_action in ["heating", "cooling"]:
            bar = "█" * 15 + "░" * 5
            lines.append("")
            lines.append(f"[{status_color}]{bar}[/] Active")

        return "\n".join(lines)

    def _render_light(self) -> str:
        """Render light entity with brightness and color visualization."""
        entity_id = self.entity.get("entity_id", "Unknown")
        state = self.entity.get("state", "off")
        attrs = self.entity.get("attributes", {})

        # Status
        is_on = state == "on"
        status_color = "yellow" if is_on else "dim"
        status_icon = "💡" if is_on else "⚫"
        status_text = "ON" if is_on else "OFF"

        lines = [
            f"[bold]{entity_id}[/]",
            "",
            f"[{status_color} bold]{status_icon} {status_text}[/]",
            "",
        ]

        if is_on:
            # Brightness
            brightness = attrs.get("brightness", None)
            if brightness is not None:
                # Convert 0-255 to 0-100%
                brightness_pct = int((brightness / 255) * 100)
                bar_length = 20
                filled = int((brightness_pct / 100) * bar_length)
                bar = "█" * filled + "░" * (bar_length - filled)
                lines.append(f"[bold white]Brightness:[/] {brightness_pct}%")
                lines.append(f"[yellow]{bar}[/]")
                lines.append("")

            # Color information
            color_mode = attrs.get("color_mode", None)
            if color_mode == "color_temp":
                color_temp = attrs.get("color_temp", None)
                if color_temp:
                    # Warmer = lower Kelvin, Cooler = higher Kelvin
                    kelvin = int(1000000 / color_temp) if color_temp > 0 else 0
                    lines.append(f"[bold white]Color:[/] {kelvin}K")
                    # Visual warmth indicator
                    if kelvin < 3000:
                        lines.append("[red]████████████████[/]░░░░ Warm")
                    elif kelvin < 4000:
                        lines.append("[yellow]████████████[/]░░░░░░░░ Neutral")
                    else:
                        lines.append("[blue]████████[/]░░░░░░░░░░░░ Cool")
            elif color_mode in ["rgb", "rgbw", "rgbww"]:
                rgb_color = attrs.get("rgb_color", None)
                if rgb_color:
                    r, g, b = rgb_color
                    lines.append(f"[bold white]Color:[/] RGB({r}, {g}, {b})")
                    lines.append(f"[rgb({r},{g},{b})]████████████████████[/]")

        # Power consumption if available
        power = attrs.get("power", None)
        if power:
            lines.append("")
            lines.append(f"[dim]Power:[/] {power}W")

        return "\n".join(lines)

    def _render_switch(self) -> str:
        """Render switch entity with large status indicator."""
        entity_id = self.entity.get("entity_id", "Unknown")
        state = self.entity.get("state", "off")
        attrs = self.entity.get("attributes", {})

        # Status
        is_on = state == "on"
        status_color = "green" if is_on else "dim"
        status_icon = "⚡" if is_on else "⭕"
        status_text = "ON" if is_on else "OFF"

        lines = [
            f"[bold]{entity_id}[/]",
            "",
            f"[{status_color} bold]{status_icon} {status_text}[/]",
            "",
        ]

        # Power consumption
        power = attrs.get("current_power_w", attrs.get("power", None))
        if power:
            lines.append(f"[bold white]Power:[/] {power}W")
            lines.append("")

        # Device class for context
        device_class = attrs.get("device_class", None)
        if device_class:
            lines.append(f"[dim]Type:[/] {device_class.replace('_', ' ').title()}")

        return "\n".join(lines)

    def _render_generic(self) -> str:
        """Fallback renderer for unknown entity types."""
        entity_id = self.entity.get("entity_id", "Unknown")
        state = self.entity.get("state", "Unknown")
        attributes = self.entity.get("attributes", {})

        lines = [
            f"[bold]{entity_id}[/]",
            f"[bold white]State:[/] [yellow]{state}[/]",
            "",
        ]

        # Show key attributes
        key_attrs = ["friendly_name", "unit_of_measurement", "device_class"]
        for key in key_attrs:
            if key in attributes and key != "friendly_name":
                lines.append(f"[cyan]{key}:[/] {attributes[key]}")

        # Show other attributes
        other_attrs = {k: v for k, v in attributes.items()
                      if k not in key_attrs and not k.startswith("_")}
        if other_attrs:
            lines.append("")
            lines.append("[bold]Attributes:[/]")
            for key, value in list(other_attrs.items())[:10]:  # Limit to 10
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."
                lines.append(f"  [dim]{key}:[/] {value_str}")

        return "\n".join(lines)


class ControlPanel(Container):
    """Panel with controls for the selected entity."""

    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        """Compose control panel widgets."""
        with Vertical():
            yield Label("Controls", id="control-label")

            # Light controls
            with Horizontal(id="light-controls", classes="control-section"):
                yield Button("On", id="btn-light-on", variant="success")
                yield Button("Off", id="btn-light-off", variant="error")
                yield Button("Toggle", id="btn-light-toggle")

            # Climate controls
            with Horizontal(id="climate-controls", classes="control-section"):
                yield Input(placeholder="Temperature", id="input-temp")
                yield Button("Set Temp", id="btn-set-temp", variant="primary")

            # HVAC mode buttons
            with Horizontal(id="hvac-modes", classes="control-section"):
                yield Button("Heat", id="btn-hvac-heat")
                yield Button("Cool", id="btn-hvac-cool")
                yield Button("Off", id="btn-hvac-off")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        selected_entity = self.app_ref.selected_entity

        if not selected_entity:
            self.app_ref.notify("No entity selected", severity="warning")
            return

        entity_id = selected_entity["entity_id"]
        api = self.app_ref.api

        try:
            # Light controls
            if button_id == "btn-light-on":
                await api.turn_on_light(entity_id)
                self.app_ref.notify(f"Turned on {entity_id}")

            elif button_id == "btn-light-off":
                await api.turn_off_light(entity_id)
                self.app_ref.notify(f"Turned off {entity_id}")

            elif button_id == "btn-light-toggle":
                await api.toggle_light(entity_id)
                self.app_ref.notify(f"Toggled {entity_id}")

            # Climate controls
            elif button_id == "btn-set-temp":
                temp_input = self.query_one("#input-temp", Input)
                try:
                    temp = float(temp_input.value)
                    await api.set_temperature(entity_id, temp)
                    self.app_ref.notify(f"Set temperature to {temp}°")
                except ValueError:
                    self.app_ref.notify("Invalid temperature", severity="error")

            elif button_id == "btn-hvac-heat":
                await api.set_hvac_mode(entity_id, "heat")
                self.app_ref.notify(f"Set {entity_id} to heat mode")

            elif button_id == "btn-hvac-cool":
                await api.set_hvac_mode(entity_id, "cool")
                self.app_ref.notify(f"Set {entity_id} to cool mode")

            elif button_id == "btn-hvac-off":
                await api.set_hvac_mode(entity_id, "off")
                self.app_ref.notify(f"Turned off {entity_id}")

        except Exception as e:
            self.app_ref.notify(f"Error: {e}", severity="error")
            logger.error(f"Control error: {e}")


class HomeAssistantTUI(App):
    """Main TUI application with vim navigation and command mode."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 2fr 1fr;
        grid-rows: auto auto 1fr;
    }

    Header {
        column-span: 2;
    }

    #connection-status {
        height: 1;
        column-span: 2;
        background: $panel;
        padding: 0 1;
    }

    #filter-bar {
        height: 1;
        column-span: 2;
        background: $boost;
        padding: 0 1;
    }

    EntityList {
        border: solid $primary;
        height: 100%;
    }

    #details-panel {
        border: thick $accent;
        padding: 2 3;
        height: 100%;
        overflow-y: auto;
        background: $surface;
    }

    #control-panel {
        display: none;
    }

    .control-section {
        height: auto;
        margin: 1 0;
    }

    Button {
        margin: 0 1;
    }

    Input {
        width: 15;
        margin: 0 1;
    }

    Footer {
        column-span: 2;
    }

    #command-line {
        display: none;
        dock: bottom;
        height: 3;
        background: $panel;
        border-top: solid $accent;
        layout: horizontal;
        padding: 0;
        layer: overlay;
    }

    #cmd-prefix {
        width: 5;
        height: 1;
        content-align: center middle;
        background: $panel;
        padding: 0 1;
    }

    #cmd-input {
        width: 1fr;
        height: 1;
        border: none;
        background: $panel;
        padding: 0 1;
    }

    /* Context Menu Styles */
    ContextMenu {
        align: center middle;
    }

    #context-menu-container {
        width: 50;
        height: auto;
        max-height: 30;
        background: $surface;
        border: thick $primary;
        padding: 0 1;
    }

    #context-menu-title {
        text-align: center;
        margin-bottom: 0;
        padding: 0;
    }

    #context-menu-items {
        height: auto;
        max-height: 25;
        padding: 0;
    }

    #context-menu-items Button {
        width: 100%;
        margin: 0;
        min-height: 1;
        height: auto;
        padding: 0 1;
    }

    #context-menu-items Input {
        width: 100%;
        margin: 0;
        height: 1;
    }

    #context-menu-items Label {
        margin: 0;
        padding: 0;
    }

    /* Temperature Input Dialog */
    TemperatureInputDialog {
        align: center middle;
    }

    #temp-dialog-container {
        width: 40;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #temp-dialog-title {
        text-align: center;
        margin-bottom: 1;
    }

    #temp-dialog-input {
        width: 100%;
        margin-bottom: 1;
    }

    #temp-dialog-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #temp-dialog-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "connect", "Connect"),
        # Vim navigation
        Binding("j", "navigate_down", "Down", show=False),
        Binding("k", "navigate_up", "Up", show=False),
        Binding("h", "navigate_left", "Left", show=False),
        Binding("l", "navigate_right", "Right", show=False),
        Binding("g", "vim_g", "Top (gg)", show=False),
        Binding("G", "jump_bottom", "Bottom", show=False),
        # Actions
        Binding("f", "toggle_favorite", "Favorite", show=False),
        Binding("space", "context_menu", "Menu", show=False),
        # Note: : and / are handled in on_key() due to Textual key naming
        Binding("n", "search_next", "Next", show=False),
        Binding("N", "search_prev", "Previous", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.ws: Optional[HomeAssistantWebSocket] = None
        self.api: Optional[HomeAssistantAPI] = None
        self.entities: Dict[str, Any] = {}
        self.selected_entity: Optional[Dict[str, Any]] = None
        self.context_menu_entity_id: Optional[str] = None  # Entity for context menu actions

        # Favorites
        self.favorites: Set[str] = set(self.config.app.favorites)

        # Filtering and grouping
        self.current_filter: FilterMode = FilterMode.ALL
        self.current_group: GroupMode = GroupMode.FAVORITES_FIRST
        self.search_term: str = ""

        # vim gg handling
        self.last_g_time: float = 0

    def compose(self) -> ComposeResult:
        """Compose the UI layout."""
        yield Header()
        yield ConnectionStatus(id="connection-status")
        yield FilterBar(id="filter-bar")
        yield EntityList(id="entity-list")
        yield EntityVisualization(id="details-panel")
        yield ControlPanel(app_ref=self, id="control-panel")
        yield CommandLine(id="command-line")
        yield Footer()

    async def on_mount(self):
        """Initialize and connect when app starts."""
        self.title = "Home Assistant TUI"
        await self.action_connect()

    async def on_key(self, event) -> None:
        """Handle key presses for command line triggers."""
        # Handle : for command mode
        if event.key == "colon":
            self.action_command_mode()
            event.prevent_default()
            event.stop()
        # Handle / for search mode
        elif event.key == "slash":
            self.action_search_mode()
            event.prevent_default()
            event.stop()

    async def action_connect(self):
        """Connect to Home Assistant."""
        status = self.query_one(ConnectionStatus)
        status.status = "Connecting"

        try:
            # Create WebSocket client
            self.ws = HomeAssistantWebSocket(
                self.config.hass_url,
                self.config.hass_token
            )

            # Connect and authenticate
            connected = await self.ws.connect()

            if not connected:
                status.status = "Disconnected"
                self.notify("Failed to connect", severity="error")
                return

            status.status = "Connected"
            self.api = HomeAssistantAPI(self.ws)

            # Subscribe to state changes for real-time updates
            await self.api.subscribe_state_changes(self._on_state_changed)

            # Load initial entities
            await self.action_refresh()

            self.notify("Connected to Home Assistant", severity="information")

        except Exception as e:
            logger.error(f"Connection error: {e}")
            status.status = "Disconnected"
            self.notify(f"Connection error: {e}", severity="error")

    async def action_refresh(self):
        """Refresh entity list with current filters and grouping."""
        if not self.api:
            self.notify("Not connected", severity="warning")
            return

        try:
            states = await self.api.get_states()

            # Filter to configured domains
            allowed_domains = tuple(f"{d}." for d in self.config.app.filters.domains)
            self.entities = {
                state["entity_id"]: state
                for state in states
                if state["entity_id"].startswith(allowed_domains)
            }

            # Update filter counts
            self._update_filter_counts()

            # Update table with filtered and sorted entities
            self._update_entity_table()

            self.notify(f"Loaded {len(self.entities)} entities")

        except Exception as e:
            logger.error(f"Refresh error: {e}")
            self.notify(f"Refresh error: {e}", severity="error")

    def _update_filter_counts(self):
        """Update entity counts for filter bar."""
        counts = {
            "all": len(self.entities),
            "favorites": sum(1 for e in self.entities if e in self.favorites),
            "lights": sum(1 for e in self.entities if e.startswith("light.")),
            "climate": sum(1 for e in self.entities if e.startswith("climate.")),
            "switches": sum(1 for e in self.entities if e.startswith("switch.")),
        }

        filter_bar = self.query_one(FilterBar)
        filter_bar.counts = counts
        filter_bar.current_filter = self.current_filter.value

    def _get_filtered_entities(self) -> List[tuple]:
        """Get filtered entity list based on current filter mode."""
        entities = []

        for entity_id, state in self.entities.items():
            # Apply filter
            if self.current_filter == FilterMode.FAVORITES:
                if entity_id not in self.favorites:
                    continue
            elif self.current_filter == FilterMode.LIGHTS:
                if not entity_id.startswith("light."):
                    continue
            elif self.current_filter == FilterMode.CLIMATE:
                if not entity_id.startswith("climate."):
                    continue
            elif self.current_filter == FilterMode.SWITCHES:
                if not entity_id.startswith("switch."):
                    continue

            # Apply search filter
            if self.search_term and self.search_term.lower() not in entity_id.lower():
                continue

            domain = entity_id.split(".")[0]
            is_favorite = entity_id in self.favorites
            fav_marker = "★" if is_favorite else ""

            entities.append((entity_id, state["state"], domain, is_favorite, fav_marker))

        return entities

    def _sort_entities(self, entities: List[tuple]) -> List[tuple]:
        """Sort entities based on current group mode."""
        if self.current_group == GroupMode.FAVORITES_FIRST:
            # Sort by: favorites first, then alphabetically
            return sorted(entities, key=lambda x: (not x[3], x[0]))
        elif self.current_group == GroupMode.TYPE:
            # Sort by domain, then name
            return sorted(entities, key=lambda x: (x[2], x[0]))
        elif self.current_group == GroupMode.STATE:
            # Sort by state, then name
            return sorted(entities, key=lambda x: (x[1], x[0]))
        elif self.current_group == GroupMode.ROOM:
            # Sort by room (from friendly_name), then name
            # This is a simplification - real room sorting would need entity registry
            return sorted(entities, key=lambda x: x[0])
        else:
            return sorted(entities, key=lambda x: x[0])

    def _update_entity_table(self):
        """Update entity table with current filters and sorting."""
        table = self.query_one(EntityList)
        table.clear()

        entities = self._get_filtered_entities()
        entities = self._sort_entities(entities)

        for entity_id, state, domain, is_favorite, fav_marker in entities:
            table.add_row(fav_marker, entity_id, state, domain, key=entity_id)

        # Auto-display first entity if table has rows
        if table.row_count > 0:
            self._update_details_from_cursor()

    def _update_details_from_cursor(self):
        """Update details panel with entity at cursor position."""
        table = self.query_one(EntityList)

        # Check if cursor is on a valid row
        if table.cursor_row is None or table.row_count == 0:
            return

        # Get row keys and ensure cursor position is valid
        row_keys = list(table.rows.keys())
        if table.cursor_row >= len(row_keys):
            return

        # Get entity from highlighted row
        row_key = row_keys[table.cursor_row]
        row = table.get_row(row_key)

        # Column 1 is entity_id (0 is favorite marker)
        entity_id = str(row[1])
        entity = self.entities.get(entity_id)

        if entity:
            self.selected_entity = entity
            details = self.query_one(EntityVisualization)
            details.entity = entity

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Handle entity selection."""
        table = self.query_one(EntityList)
        row_key = event.row_key
        row = table.get_row(row_key)

        # Column 1 is entity_id (0 is favorite marker)
        entity_id = str(row[1])
        self.selected_entity = self.entities.get(entity_id)

        # Update details panel
        details = self.query_one(EntityVisualization)
        details.entity = self.selected_entity

    # Vim Navigation Actions

    def action_navigate_down(self) -> None:
        """Navigate down (j key)."""
        table = self.query_one(EntityList)
        table.action_cursor_down()
        self._update_details_from_cursor()

    def action_navigate_up(self) -> None:
        """Navigate up (k key)."""
        table = self.query_one(EntityList)
        table.action_cursor_up()
        self._update_details_from_cursor()

    def action_navigate_left(self) -> None:
        """Navigate left (h key)."""
        pass  # Could be used for collapsing panels in future

    def action_navigate_right(self) -> None:
        """Navigate right / select (l key)."""
        table = self.query_one(EntityList)
        if table.cursor_row is not None:
            table.action_select_cursor()

    def action_vim_g(self) -> None:
        """Handle 'g' key press for gg (jump to top)."""
        import time
        current_time = time.time()

        # Double-tap 'g' within 0.5 seconds = jump to top
        if current_time - self.last_g_time < 0.5:
            self.action_jump_top()
            self.last_g_time = 0  # Reset
        else:
            self.last_g_time = current_time

    def action_jump_top(self) -> None:
        """Jump to top of list (gg)."""
        table = self.query_one(EntityList)
        if table.row_count > 0:
            table.move_cursor(row=0)
            self._update_details_from_cursor()

    def action_jump_bottom(self) -> None:
        """Jump to bottom of list (G)."""
        table = self.query_one(EntityList)
        if table.row_count > 0:
            table.move_cursor(row=table.row_count - 1)
            self._update_details_from_cursor()

    # Search Actions

    def action_search_mode(self) -> None:
        """Enter search mode (/)."""
        cmd_line = self.query_one(CommandLine)
        cmd_line.show(mode="search")

    def action_search_next(self) -> None:
        """Jump to next search result (n)."""
        if not self.search_term:
            self.notify("No active search", severity="warning")
            return
        # Re-apply search filter and jump to next
        self._update_entity_table()

    def action_search_prev(self) -> None:
        """Jump to previous search result (N)."""
        if not self.search_term:
            self.notify("No active search", severity="warning")
            return
        # Re-apply search filter and jump to previous
        self._update_entity_table()

    # Command Mode Actions

    def action_command_mode(self) -> None:
        """Enter command mode (:)."""
        cmd_line = self.query_one(CommandLine)
        cmd_line.show(mode="command")

    async def on_command_line_search_updated(self, message: CommandLine.SearchUpdated) -> None:
        """Handle live search updates as user types."""
        self.search_term = message.search_term
        self._update_entity_table()

    async def on_command_line_command_submitted(self, message: CommandLine.CommandSubmitted) -> None:
        """Handle submitted commands and searches."""
        command = message.command.strip()

        if not command:
            return

        # Handle search mode (Enter key pressed)
        if message.mode == "search":
            self.search_term = command
            self._update_entity_table()
            matched_count = self.query_one(EntityList).row_count
            self.notify(f"Search: {command} ({matched_count} results)")
            return

        # Handle command mode
        # Parse command
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Execute command
        if cmd in ["q", "quit"]:
            await self.action_quit()

        elif cmd in ["fav", "favorites"]:
            self.current_filter = FilterMode.FAVORITES
            self._update_filter_counts()
            self._update_entity_table()
            self.notify("Showing favorites only")

        elif cmd == "all":
            self.current_filter = FilterMode.ALL
            self.search_term = ""
            self._update_filter_counts()
            self._update_entity_table()
            self.notify("Showing all entities")

        elif cmd == "lights":
            self.current_filter = FilterMode.LIGHTS
            self._update_filter_counts()
            self._update_entity_table()
            self.notify("Showing lights only")

        elif cmd == "climate":
            self.current_filter = FilterMode.CLIMATE
            self._update_filter_counts()
            self._update_entity_table()
            self.notify("Showing climate entities only")

        elif cmd == "switches":
            self.current_filter = FilterMode.SWITCHES
            self._update_filter_counts()
            self._update_entity_table()
            self.notify("Showing switches only")

        elif cmd == "search" and args:
            self.search_term = args
            self._update_entity_table()
            matched_count = self.query_one(EntityList).row_count
            self.notify(f"Search: {args} ({matched_count} results)")

        elif cmd == "group":
            if args == "type":
                self.current_group = GroupMode.TYPE
                self._update_entity_table()
                self.notify("Grouping by type")
            elif args == "state":
                self.current_group = GroupMode.STATE
                self._update_entity_table()
                self.notify("Grouping by state")
            elif args == "room":
                self.current_group = GroupMode.ROOM
                self._update_entity_table()
                self.notify("Grouping by room")
            elif args == "favorites_first":
                self.current_group = GroupMode.FAVORITES_FIRST
                self._update_entity_table()
                self.notify("Showing favorites first")
            else:
                self.notify(f"Unknown group mode: {args}", severity="error")

        else:
            self.notify(f"Unknown command: {cmd}", severity="error")

    # Favorites Actions

    def action_toggle_favorite(self) -> None:
        """Toggle favorite status for selected entity (f key)."""
        if not self.selected_entity:
            self.notify("No entity selected", severity="warning")
            return

        entity_id = self.selected_entity["entity_id"]

        if entity_id in self.favorites:
            self.favorites.remove(entity_id)
            self.notify(f"Removed from favorites: {entity_id}")
        else:
            self.favorites.add(entity_id)
            self.notify(f"Added to favorites: {entity_id}")

        # Save to config
        self._save_favorites()

        # Refresh table to update star markers
        self._update_filter_counts()
        self._update_entity_table()

    def _save_favorites(self) -> None:
        """Save favorites to user config file."""
        try:
            self.config.app.favorites = list(self.favorites)
            save_user_config(self.config.app)
        except Exception as e:
            logger.error(f"Failed to save favorites: {e}")
            self.notify("Failed to save favorites", severity="error")

    # Context Menu Actions

    def action_context_menu(self) -> None:
        """Show context menu for highlighted entity (spacebar)."""
        table = self.query_one(EntityList)

        # Get entity from highlighted row (cursor position)
        if table.cursor_row is None:
            self.notify("No entity highlighted", severity="warning")
            return

        # Get the row key at cursor position
        row_keys = list(table.rows.keys())
        if table.cursor_row >= len(row_keys):
            return

        row_key = row_keys[table.cursor_row]
        row = table.get_row(row_key)

        # Column 1 is entity_id (0 is favorite marker)
        entity_id = str(row[1])
        entity = self.entities.get(entity_id)

        if not entity:
            self.notify("Entity not found", severity="error")
            return

        # Store for context menu actions
        self.context_menu_entity_id = entity_id
        is_favorite = entity_id in self.favorites

        # Show modal with callback
        self.push_screen(
            ContextMenu(entity, is_favorite),
            callback=self._handle_context_menu_callback
        )

    def _handle_context_menu_callback(self, result) -> None:
        """Handle result from context menu modal."""
        if result:
            # Result can be a string (action_id) or tuple (action_id, data)
            if isinstance(result, tuple):
                action_id, data = result
                self.run_worker(self._handle_context_menu_action(action_id, data))
            else:
                self.run_worker(self._handle_context_menu_action(result, None))

    async def _handle_context_menu_action(self, action_id: str, data: Optional[str] = None) -> None:
        """Handle action from context menu."""
        if not self.context_menu_entity_id:
            return

        entity_id = self.context_menu_entity_id
        entity = self.entities.get(entity_id)

        if not entity:
            return

        try:
            if action_id == "ctx-toggle-fav":
                # Toggle favorite for context menu entity
                if entity_id in self.favorites:
                    self.favorites.remove(entity_id)
                    self.notify(f"Removed from favorites: {entity_id}")
                else:
                    self.favorites.add(entity_id)
                    self.notify(f"Added to favorites: {entity_id}")
                self._save_favorites()
                self._update_filter_counts()
                self._update_entity_table()

            elif action_id == "ctx-light-on":
                await self.api.turn_on_light(entity_id)
                self.notify(f"Turned on {entity_id}")

            elif action_id == "ctx-light-off":
                await self.api.turn_off_light(entity_id)
                self.notify(f"Turned off {entity_id}")

            elif action_id == "ctx-light-toggle":
                await self.api.toggle_light(entity_id)
                self.notify(f"Toggled {entity_id}")

            elif action_id == "ctx-switch-on":
                await self.api.turn_on_light(entity_id)  # Same API
                self.notify(f"Turned on {entity_id}")

            elif action_id == "ctx-switch-off":
                await self.api.turn_off_light(entity_id)
                self.notify(f"Turned off {entity_id}")

            elif action_id == "ctx-switch-toggle":
                await self.api.toggle_light(entity_id)
                self.notify(f"Toggled {entity_id}")

            elif action_id == "ctx-set-temp":
                # Set temperature from context menu input
                if data:
                    try:
                        temp = float(data)
                        await self.api.set_temperature(entity_id, temp)
                        self.notify(f"Set temperature to {temp}°")
                    except ValueError:
                        self.notify("Invalid temperature", severity="error")
                else:
                    self.notify("No temperature provided", severity="warning")

            elif action_id == "ctx-hvac-heat":
                await self.api.set_hvac_mode(entity_id, "heat")
                self.notify(f"Set {entity_id} to heat mode")

            elif action_id == "ctx-hvac-cool":
                await self.api.set_hvac_mode(entity_id, "cool")
                self.notify(f"Set {entity_id} to cool mode")

            elif action_id == "ctx-hvac-off":
                await self.api.set_hvac_mode(entity_id, "off")
                self.notify(f"Turned off {entity_id}")

            elif action_id == "ctx-details":
                # Just close the menu, details already shown
                pass

        except Exception as e:
            logger.error(f"Context menu action error: {e}")
            self.notify(f"Error: {e}", severity="error")

    async def _on_state_changed(self, event: Dict[str, Any]):
        """
        Handle state change events from WebSocket.

        REAL-TIME UPDATES:
        ------------------
        This callback is invoked whenever an entity's state changes.
        We update our local cache and refresh the UI.
        """
        data = event.get("data", {})
        entity_id = data.get("entity_id")
        new_state = data.get("new_state")

        if not entity_id or not new_state:
            return

        # Only process entities we care about
        allowed_domains = tuple(f"{d}." for d in self.config.app.filters.domains)
        if not entity_id.startswith(allowed_domains):
            return

        # Update local cache
        self.entities[entity_id] = new_state

        # Update table if this entity is displayed
        table = self.query_one(EntityList)
        try:
            table.update_cell(entity_id, "State", new_state["state"])
        except KeyError:
            pass  # Entity not displayed in current view

        # Update details if this is the selected entity
        if self.selected_entity and self.selected_entity["entity_id"] == entity_id:
            self.selected_entity = new_state
            details = self.query_one(EntityVisualization)
            details.entity = new_state

    async def action_quit(self):
        """Quit the application."""
        if self.ws:
            await self.ws.close()
        await super().action_quit()


def run():
    """Entry point for the application."""
    app = HomeAssistantTUI()
    app.run()
