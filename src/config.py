#!/usr/bin/env python3
"""Configuration module to load environment variables."""
import os
from pathlib import Path


def load_env():
    """Load environment variables from .env file."""
    # Look for .env file in project root (parent of src)
    env_file = Path(__file__).parent.parent / ".env"

    if not env_file.exists():
        return

    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip().strip('"').strip("'")
                os.environ[key.strip()] = value


# Auto-load on import
load_env()
