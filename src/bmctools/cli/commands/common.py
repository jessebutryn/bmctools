"""Common command utilities shared across all commands."""

import sys
from bmctools.cli.formatters import format_output
from bmctools.cli.utils import (
    handle_error,
    get_exit_code,
    print_verbose,
    print_success
)


def wrap_command(func, args):
    """Wrap command execution with common error handling.

    Args:
        func: Command function to execute
        args: Parsed arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        result = func(args)
        if result is not None:
            output = format_output(result, args.output)
            print(output)
        return 0
    except Exception as e:
        handle_error(e, args)
        return get_exit_code(e)


def read_file_lines(file_path):
    """Read lines from a file.

    Args:
        file_path: Path to file

    Returns:
        List of lines (stripped of whitespace)

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    try:
        with open(file_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise ValueError(f"Failed to read file {file_path}: {e}")


def parse_comma_list(value):
    """Parse comma-separated list.

    Args:
        value: Comma-separated string

    Returns:
        List of strings
    """
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


def confirm_action(prompt, force=False):
    """Prompt user for confirmation on destructive operations.

    Args:
        prompt: Confirmation prompt message
        force: If True, skip confirmation and return True

    Returns:
        True if confirmed, False otherwise
    """
    if force:
        return True

    try:
        response = input(f"{prompt} [y/N]: ").strip().lower()
        return response in ('y', 'yes')
    except (KeyboardInterrupt, EOFError):
        print()  # New line after interrupt
        return False


def show_progress(message, done=False):
    """Display progress indicator.

    Args:
        message: Progress message
        done: If True, show completion, else show in-progress
    """
    if done:
        print(f"✓ {message}", file=sys.stderr)
    else:
        print(f"⋯ {message}...", file=sys.stderr, end='', flush=True)


def validate_file_exists(file_path):
    """Validate that a file exists.

    Args:
        file_path: Path to file

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    import os
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"Not a file: {file_path}")


def parse_key_value_pairs(pairs):
    """Parse key=value pairs from list of strings.

    Args:
        pairs: List of "key=value" strings

    Returns:
        Dict of key-value pairs

    Raises:
        ValueError: If format is invalid
    """
    result = {}
    for pair in pairs:
        if '=' not in pair:
            raise ValueError(f"Invalid key=value format: {pair}")
        key, value = pair.split('=', 1)
        result[key.strip()] = value.strip()
    return result
