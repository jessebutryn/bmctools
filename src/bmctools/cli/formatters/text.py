"""Text output formatter."""


def format_text(data):
    """Format data as simple text.

    Args:
        data: Data to format (scalar, string, or simple structure)

    Returns:
        Text string
    """
    if isinstance(data, (str, int, float, bool)):
        return str(data)
    elif isinstance(data, list):
        return '\n'.join(str(item) for item in data)
    elif isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{key}:")
                if isinstance(value, dict):
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
                else:
                    for item in value:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        return '\n'.join(lines)
    else:
        return str(data)
