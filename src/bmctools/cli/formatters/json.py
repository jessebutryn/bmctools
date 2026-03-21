"""JSON output formatter."""

import json
from typing import Any


def format_json(data: Any, pretty: bool = False) -> str:
    """Format data as JSON.

    Args:
        data: Data to format (must be JSON-serializable)
        pretty: If True, use indentation and sort keys

    Returns:
        JSON string
    """
    if pretty:
        return json.dumps(data, indent=4, sort_keys=True)
    else:
        return json.dumps(data)
