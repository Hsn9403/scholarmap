#!/usr/bin/env python3
"""
Cassette system for recording and replaying API responses.

This module provides a way to:
- Record API responses to JSON files during online mode
- Replay recorded responses during offline mode (no API calls)

Usage:
    # Record mode (default): makes real API calls AND saves responses
    cassette = CassetteManager(mode="record")

    # Offline mode: only uses cached responses, no API calls
    cassette = CassetteManager(mode="offline")

    # Disabled: no caching, always makes real API calls
    cassette = CassetteManager(mode="disabled")

The cassette files are stored in: src/api/cassettes/
Each file is named with a hash of the request parameters.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.logger import logger


# Default cassette directory (relative to this file)
CASSETTE_DIR = Path(__file__).parent / "cassettes"


class CassetteManager:
    """
    Manages recording and playback of API responses.

    Attributes:
        mode: Operating mode - "record", "offline", or "disabled"
        cassette_dir: Directory where cassette files are stored

    Example:
        >>> manager = CassetteManager(mode="record")
        >>>
        >>> # Try to get cached response
        >>> cached = manager.get(params)
        >>> if cached:
        >>>     return cached
        >>>
        >>> # Make real API call
        >>> response = real_api_call(params)
        >>>
        >>> # Save for future offline use
        >>> manager.save(params, response)
    """

    # Valid modes
    MODE_RECORD = "record"      # Make real calls + save responses
    MODE_OFFLINE = "offline"    # Only use cached responses
    MODE_DISABLED = "disabled"  # No caching at all

    def __init__(
        self,
        mode: str = "record",
        cassette_dir: Optional[Path] = None
    ):
        """
        Initialize the cassette manager.

        Args:
            mode: Operating mode:
                - "record": Make real API calls AND save responses
                - "offline": Only use cached responses (no API calls)
                - "disabled": No caching, always make real API calls
            cassette_dir: Directory for cassette files (default: src/api/cassettes/)
        """
        self.mode = mode
        self.cassette_dir = cassette_dir or CASSETTE_DIR

        # Create cassette directory if needed
        if self.mode != self.MODE_DISABLED:
            self.cassette_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"CassetteManager initialized (mode={mode}, dir={self.cassette_dir})")

    def _make_key(self, params: Dict[str, Any]) -> str:
        """
        Generate a unique key for the given parameters.

        The key is a SHA256 hash of the sorted, serialized parameters.
        We exclude 'api_key' from the hash since it's sensitive and
        doesn't affect the response content.

        Args:
            params: Request parameters dict

        Returns:
            A unique string key (40 character hex string)
        """
        # Remove api_key from params for hashing (it's sensitive)
        params_for_hash = {k: v for k, v in params.items() if k != "api_key"}

        # Sort keys for consistent hashing
        serialized = json.dumps(params_for_hash, sort_keys=True, ensure_ascii=False)

        # Create SHA256 hash (truncated to 40 chars for readability)
        hash_obj = hashlib.sha256(serialized.encode("utf-8"))
        return hash_obj.hexdigest()[:40]

    def _get_cassette_path(self, key: str) -> Path:
        """Get the file path for a cassette key."""
        return self.cassette_dir / f"{key}.json"

    def get(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Try to get a cached response for the given parameters.

        Args:
            params: Request parameters dict

        Returns:
            Cached response dict if found, None otherwise
        """
        if self.mode == self.MODE_DISABLED:
            return None

        key = self._make_key(params)
        cassette_path = self._get_cassette_path(key)

        if not cassette_path.exists():
            if self.mode == self.MODE_OFFLINE:
                logger.warning(f"Cassette not found for key {key[:8]}... (offline mode)")
            return None

        try:
            with open(cassette_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.debug(f"Cassette HIT: {key[:8]}... ({cassette_path.name})")
            return data.get("response")

        except Exception as e:
            logger.warning(f"Failed to read cassette {key[:8]}...: {e}")
            return None

    def save(self, params: Dict[str, Any], response: Dict[str, Any]) -> None:
        """
        Save a response to the cassette.

        Args:
            params: Request parameters (used to generate key)
            response: API response to save
        """
        if self.mode != self.MODE_RECORD:
            return

        key = self._make_key(params)
        cassette_path = self._get_cassette_path(key)

        # Build cassette data with metadata
        cassette_data = {
            "request": {k: v for k, v in params.items() if k != "api_key"},
            "response": response,
        }

        try:
            with open(cassette_path, "w", encoding="utf-8") as f:
                json.dump(cassette_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Cassette SAVED: {key[:8]}... ({cassette_path.name})")

        except Exception as e:
            logger.warning(f"Failed to save cassette {key[:8]}...: {e}")

    def has_cassette(self, params: Dict[str, Any]) -> bool:
        """Check if a cassette exists for the given parameters."""
        if self.mode == self.MODE_DISABLED:
            return False
        key = self._make_key(params)
        return self._get_cassette_path(key).exists()

    def list_cassettes(self) -> list:
        """List all cassette files."""
        if not self.cassette_dir.exists():
            return []
        return list(self.cassette_dir.glob("*.json"))

    def clear_cassettes(self) -> int:
        """
        Delete all cassette files.

        Returns:
            Number of files deleted
        """
        count = 0
        for f in self.list_cassettes():
            f.unlink()
            count += 1
        logger.info(f"Cleared {count} cassette files")
        return count


# ---------------------------------------------------------------------------
# Module-level helper to get mode from environment
# ---------------------------------------------------------------------------

def get_cassette_mode() -> str:
    """
    Get cassette mode from environment variable.

    Environment variable: CASSETTE_MODE
    Values: "record", "offline", "disabled"
    Default: "record"

    Returns:
        Cassette mode string
    """
    mode = os.getenv("CASSETTE_MODE", "record").lower().strip()

    valid_modes = (CassetteManager.MODE_RECORD,
                   CassetteManager.MODE_OFFLINE,
                   CassetteManager.MODE_DISABLED)

    if mode not in valid_modes:
        logger.warning(f"Invalid CASSETTE_MODE '{mode}', using 'record'")
        return CassetteManager.MODE_RECORD

    return mode
