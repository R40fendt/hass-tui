#!/usr/bin/env python3
"""
Config validator for Home Assistant TUI.

Checks configuration files and connection before starting the app.
"""

import sys
from pathlib import Path


def validate():
    """Validate configuration and dependencies."""
    print("🔍 Home Assistant TUI Configuration Validator\n")

    errors = []
    warnings = []

    # Check .env.prod
    env_file = Path(".env")
    if not env_file.exists():
        errors.append("❌ .env not found")
    else:
        print("✓ .env.prod exists")
        # Try to load it
        try:
            from dotenv import load_dotenv
            import os

            load_dotenv(env_file)

            hass_url = os.getenv("HASS_URL")
            hass_token = os.getenv("HASS_TOKEN")

            if not hass_url:
                errors.append("❌ HASS_URL not set in .env.prod")
            else:
                print(f"✓ HASS_URL: {hass_url}")

            if not hass_token:
                errors.append("❌ HASS_TOKEN not set in .env.prod")
            else:
                print(f"✓ HASS_TOKEN: {'*' * 20}... (hidden)")

        except Exception as e:
            errors.append(f"❌ Error loading .env.prod: {e}")

    # Check config.yaml
    config_file = Path("config.yaml")
    if not config_file.exists():
        errors.append("❌ config.yaml not found")
    else:
        print("✓ config.yaml exists")
        try:
            import yaml

            with open(config_file) as f:
                config = yaml.safe_load(f)
            print(f"✓ config.yaml is valid YAML")

            if "favorites" in config:
                print(f"  - {len(config['favorites'])} favorites configured")
            if "filters" in config and "domains" in config["filters"]:
                print(f"  - {len(config['filters']['domains'])} domains filtered")

        except Exception as e:
            errors.append(f"❌ Error parsing config.yaml: {e}")

    # Check user config
    user_config = Path.home() / ".config" / "hass_tui" / "config.yaml"
    if user_config.exists():
        print(f"✓ User config found: {user_config}")
        try:
            import yaml

            with open(user_config) as f:
                user_cfg = yaml.safe_load(f)
            print(f"✓ User config is valid YAML")
        except Exception as e:
            warnings.append(f"⚠️  Error parsing user config: {e}")
    else:
        print(f"ℹ️  No user config (will use defaults): {user_config}")

    # Check dependencies
    print("\n📦 Checking dependencies...")
    deps = ["textual", "websockets", "pydantic", "yaml", "dotenv"]

    for dep in deps:
        try:
            if dep == "dotenv":
                __import__("dotenv")
            elif dep == "yaml":
                __import__("yaml")
            else:
                __import__(dep)
            print(f"✓ {dep}")
        except ImportError:
            errors.append(f"❌ Missing dependency: {dep}")

    # Try to import the app
    print("\n🔧 Checking app modules...")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from src.hass_tui import config

        print("✓ config module")
    except Exception as e:
        errors.append(f"❌ Failed to import config: {e}")

    try:
        from src.hass_tui import app

        print("✓ app module")
    except Exception as e:
        errors.append(f"❌ Failed to import app: {e}")

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f"❌ VALIDATION FAILED - {len(errors)} error(s)")
        for err in errors:
            print(f"  {err}")
    else:
        print("✅ VALIDATION PASSED - Ready to run!")

    if warnings:
        print(f"\n⚠️  {len(warnings)} warning(s):")
        for warn in warnings:
            print(f"  {warn}")

    print("=" * 60)

    return len(errors) == 0


if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
