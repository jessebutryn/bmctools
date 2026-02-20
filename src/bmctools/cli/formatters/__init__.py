"""Output formatters for CLI."""

from .json import format_json
from .table import format_table
from .text import format_text


def format_output(data, format_type='json'):
    """Format output data according to the specified format type.

    Args:
        data: Data to format (dict, list, or scalar)
        format_type: Output format ('json', 'json-pretty', 'table', 'text')

    Returns:
        Formatted string
    """
    if format_type == 'json':
        return format_json(data, pretty=False)
    elif format_type == 'json-pretty':
        return format_json(data, pretty=True)
    elif format_type == 'table':
        return format_table(data)
    elif format_type == 'text':
        return format_text(data)
    else:
        # Default to JSON
        return format_json(data, pretty=False)


__all__ = ['format_output', 'format_json', 'format_table', 'format_text']
