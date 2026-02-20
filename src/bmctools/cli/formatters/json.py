"""JSON output formatter."""

import json


def format_json(data, pretty=False):
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
