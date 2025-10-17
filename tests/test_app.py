"""
Unit tests for the TUI app.

These tests run in headless mode and won't corrupt your terminal.
"""
import pytest
from textual.pilot import Pilot

# NOTE: Tests are currently disabled because importing the app
# requires Home Assistant credentials. When testing is needed:
# 1. Mock the WebSocket connection
# 2. Mock the config loading
# 3. Use Textual's async test utilities with Pilot

# Example test structure (disabled):
# @pytest.mark.asyncio
# async def test_app_startup():
#     """Test that app can start in headless mode."""
#     from src.hass_tui.app import HomeAssistantTUI
#     app = HomeAssistantTUI()
#     async with app.run_test() as pilot:
#         # Test navigation, commands, etc.
#         await pilot.press("j", "k")
#         assert app.is_running

def test_placeholder():
    """Placeholder test to ensure pytest works."""
    assert True
