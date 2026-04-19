"""
data_loader.py — Central utility for safely loading JSON data files.

All modules should load data through this module to ensure consistent
error handling and graceful fallback behavior.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


def load_json(filename: str, default: Any = None) -> Any:
    """Load a JSON file from the data/ directory.

    Returns ``default`` if the file is missing, unreadable, or malformed,
    rather than raising an exception. This keeps the bot running even when
    individual data files are incomplete or absent.

    Args:
        filename: Filename within the data/ directory (e.g. "care.json").
        default: Value to return on failure. Defaults to an empty dict.

    Returns:
        Parsed JSON content, or ``default`` on any error.
    """
    if default is None:
        default = {}

    filepath = DATA_DIR / filename

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.debug(f"Loaded {filepath}")
        return data
    except FileNotFoundError:
        logger.warning(f"Data file not found: {filepath} — using default.")
        return default
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in {filepath}: {e} — using default.")
        return default
    except OSError as e:
        logger.error(f"Could not read {filepath}: {e} — using default.")
        return default
