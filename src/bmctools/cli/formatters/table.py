"""Table output formatter."""


def format_table(data, headers=None):
    """Format data as an ASCII table.

    Args:
        data: List of dicts or list of lists to format as table
        headers: Optional list of headers (auto-detected from dict keys if not provided)

    Returns:
        ASCII table string
    """
    if not data:
        return "No data"

    # Handle single dict - convert to list
    if isinstance(data, dict):
        if headers is None:
            headers = ['Key', 'Value']
        data = [[k, v] for k, v in data.items()]

    # Handle list of dicts
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        if headers is None:
            # Extract headers from first dict
            headers = list(data[0].keys())

        # Convert to list of lists
        rows = []
        for item in data:
            row = [str(item.get(h, '')) for h in headers]
            rows.append(row)
        data = rows

    # Handle list of lists
    if not isinstance(data, list) or len(data) == 0:
        return "No data"

    # If no headers provided, use column numbers
    if headers is None:
        headers = [f"Column{i}" for i in range(len(data[0]))]

    # Calculate column widths
    col_widths = [len(str(h)) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # Build format string
    format_str = " | ".join(f"{{:<{w}}}" for w in col_widths)

    # Build table
    lines = []

    # Header
    header_line = format_str.format(*[str(h) for h in headers])
    lines.append(header_line)

    # Separator
    separator = "-+-".join("-" * w for w in col_widths)
    lines.append(separator)

    # Data rows
    for row in data:
        # Ensure row has enough columns
        row_data = [str(cell) if i < len(row) else '' for i, cell in enumerate(headers)]
        for i, cell in enumerate(row):
            if i < len(row_data):
                row_data[i] = str(cell)
        line = format_str.format(*row_data[:len(headers)])
        lines.append(line)

    return '\n'.join(lines)
