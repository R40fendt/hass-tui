"""
Home Assistant API Operations

This module provides high-level operations for Home Assistant using the WebSocket client.
It translates user actions (turn on light, set temperature) into WebSocket commands.
"""

import logging
from typing import Any, Dict, List, Optional, Callable

from .websocket_client import HomeAssistantWebSocket


logger = logging.getLogger(__name__)


class HomeAssistantAPI:
    """
    High-level interface to Home Assistant via WebSocket.

    Provides methods for common operations:
    - Fetching entity states
    - Controlling devices (lights, climate)
    - Subscribing to state changes
    """

    def __init__(self, websocket: HomeAssistantWebSocket):
        """
        Initialize API wrapper.

        Args:
            websocket: Connected WebSocket client
        """
        self.ws = websocket

    async def get_states(self) -> List[Dict[str, Any]]:
        """
        Fetch all entity states from Home Assistant.

        Returns:
            List of entity state dictionaries, each containing:
            - entity_id: Unique identifier (e.g., "light.living_room")
            - state: Current state (e.g., "on", "off", "20.5")
            - attributes: Additional info (brightness, temperature, etc.)
            - last_changed: Timestamp of last state change
            - last_updated: Timestamp of last update
        """
        result = await self.ws.send_command("get_states")
        logger.info(f"Fetched {len(result)} entities")
        return result

    async def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get state of a specific entity.

        Args:
            entity_id: Entity identifier (e.g., "light.kitchen")

        Returns:
            Entity state dict or None if not found
        """
        states = await self.get_states()
        for state in states:
            if state["entity_id"] == entity_id:
                return state
        return None

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: Optional[str] = None,
        **service_data
    ) -> Any:
        """
        Call a Home Assistant service.

        SERVICES IN HOME ASSISTANT:
        ---------------------------
        Services are actions you can perform on entities. Each domain
        (light, switch, climate, etc.) has its own services.

        Examples:
        - light.turn_on: Turn on a light
        - light.turn_off: Turn off a light
        - climate.set_temperature: Set thermostat temperature

        Args:
            domain: Service domain (e.g., "light", "climate")
            service: Service name (e.g., "turn_on", "set_temperature")
            entity_id: Target entity (optional)
            **service_data: Additional service parameters

        Returns:
            Service response data
        """
        service_call = {
            "domain": domain,
            "service": service,
        }

        # Build service data
        data = {}
        if entity_id:
            data["entity_id"] = entity_id
        data.update(service_data)

        if data:
            service_call["service_data"] = data

        logger.info(f"Calling service {domain}.{service} on {entity_id}")
        result = await self.ws.send_command("call_service", **service_call)
        return result

    # ========================================================================
    # LIGHT CONTROLS
    # ========================================================================

    async def turn_on_light(
        self,
        entity_id: str,
        brightness: Optional[int] = None,
        rgb_color: Optional[tuple] = None
    ):
        """
        Turn on a light with optional brightness and color.

        Args:
            entity_id: Light entity ID
            brightness: Brightness 0-255 (optional)
            rgb_color: RGB color tuple (r, g, b) 0-255 (optional)
        """
        service_data = {}
        if brightness is not None:
            service_data["brightness"] = brightness
        if rgb_color is not None:
            service_data["rgb_color"] = list(rgb_color)

        await self.call_service("light", "turn_on", entity_id, **service_data)

    async def turn_off_light(self, entity_id: str):
        """Turn off a light."""
        await self.call_service("light", "turn_off", entity_id)

    async def toggle_light(self, entity_id: str):
        """Toggle a light (on -> off, off -> on)."""
        await self.call_service("light", "toggle", entity_id)

    # ========================================================================
    # CLIMATE CONTROLS
    # ========================================================================

    async def set_temperature(self, entity_id: str, temperature: float):
        """
        Set thermostat target temperature.

        Args:
            entity_id: Climate entity ID
            temperature: Target temperature in configured unit (C or F)
        """
        await self.call_service(
            "climate",
            "set_temperature",
            entity_id,
            temperature=temperature
        )

    async def set_hvac_mode(self, entity_id: str, hvac_mode: str):
        """
        Set HVAC mode.

        Args:
            entity_id: Climate entity ID
            hvac_mode: Mode - "off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"
        """
        await self.call_service(
            "climate",
            "set_hvac_mode",
            entity_id,
            hvac_mode=hvac_mode
        )

    # ========================================================================
    # EVENT SUBSCRIPTIONS
    # ========================================================================

    async def subscribe_state_changes(self, callback: Callable) -> int:
        """
        Subscribe to all state change events.

        REAL-TIME UPDATES:
        ------------------
        This enables live UI updates. Whenever any entity changes state,
        your callback will be invoked with the event data.

        Event data structure:
        {
            "event_type": "state_changed",
            "data": {
                "entity_id": "light.kitchen",
                "old_state": {...},
                "new_state": {...}
            }
        }

        Args:
            callback: Function to call on state changes

        Returns:
            Subscription ID
        """
        return await self.ws.subscribe_events("state_changed", callback)

    async def get_config(self) -> Dict[str, Any]:
        """
        Get Home Assistant configuration.

        Returns info about:
        - Location (latitude, longitude)
        - Units (metric/imperial)
        - Time zone
        - Version
        """
        return await self.ws.send_command("get_config")

    async def get_services(self) -> Dict[str, Any]:
        """
        Get all available services.

        Useful for discovering what actions are possible.
        """
        return await self.ws.send_command("get_services")
