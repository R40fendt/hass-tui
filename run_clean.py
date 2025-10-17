#!/usr/bin/env python3
"""
Clean runner for Home Assistant TUI.
No logging output - just the TUI.
"""

import logging
import sys

# Disable all logging output to keep TUI clean
logging.basicConfig(level=logging.CRITICAL)

# Disable websockets library debug output
logging.getLogger('websockets').setLevel(logging.CRITICAL)
logging.getLogger('asyncio').setLevel(logging.CRITICAL)

from src.hass_tui.app import run

if __name__ == "__main__":
    run()
