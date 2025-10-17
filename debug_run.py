#!/usr/bin/env python3
"""
Debug runner for Home Assistant TUI.

This script runs the TUI with enhanced logging and error reporting.
Logs are written to logs/ folder with timestamps.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Set up debug logging before importing the app
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"debug_{timestamp}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w')
    ]
)

logger = logging.getLogger(__name__)

logger.info("=" * 80)
logger.info("Starting Home Assistant TUI in DEBUG mode")
logger.info(f"Log file: {log_file}")
logger.info("=" * 80)

try:
    from src.hass_tui.app import run

    logger.info("App imported successfully")
    logger.info("Starting TUI application...")

    run()

except Exception as e:
    logger.exception("Fatal error during startup or execution:")
    print(f"\n\n{'='*80}")
    print("FATAL ERROR - Check debug.log for details")
    print(f"{'='*80}")
    print(f"Error: {e}")
    print(f"\nFull traceback in: {log_file}")
    sys.exit(1)
finally:
    logger.info("Application shutdown")
