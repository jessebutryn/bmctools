"""CLI utilities for bmctools."""

import os
import sys


# Exit codes
EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_CONNECTION_ERROR = 2
EXIT_NOT_IMPLEMENTED = 3
EXIT_INVALID_ARGUMENTS = 4
EXIT_FILE_NOT_FOUND = 5
EXIT_TIMEOUT = 6


# ANSI color codes
class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'


def is_tty():
    """Check if stdout is a TTY (supports colors)."""
    return sys.stdout.isatty()


def should_use_color(args):
    """Determine if color output should be used.

    Args:
        args: Parsed arguments with no_color attribute

    Returns:
        True if colors should be used, False otherwise
    """
    # Check NO_COLOR environment variable
    if os.environ.get('NO_COLOR'):
        return False

    # Check command-line flag
    if hasattr(args, 'no_color') and args.no_color:
        return False

    # Check if output is a TTY
    return is_tty()


def colorize(text, color, args=None):
    """Colorize text if color output is enabled.

    Args:
        text: Text to colorize
        color: Color code from Colors class
        args: Parsed arguments (optional)

    Returns:
        Colorized text if colors enabled, plain text otherwise
    """
    if args and not should_use_color(args):
        return text

    if not is_tty():
        return text

    return f"{color}{text}{Colors.RESET}"


def print_error(message, args=None):
    """Print error message to stderr.

    Args:
        message: Error message
        args: Parsed arguments (optional)
    """
    colored_msg = colorize(f"Error: {message}", Colors.RED, args)
    print(colored_msg, file=sys.stderr)


def print_warning(message, args=None):
    """Print warning message to stderr.

    Args:
        message: Warning message
        args: Parsed arguments (optional)
    """
    colored_msg = colorize(f"Warning: {message}", Colors.YELLOW, args)
    print(colored_msg, file=sys.stderr)


def print_success(message, args=None):
    """Print success message to stdout.

    Args:
        message: Success message
        args: Parsed arguments (optional)
    """
    colored_msg = colorize(message, Colors.GREEN, args)
    print(colored_msg)


def print_verbose(message, args):
    """Print verbose message if verbose mode is enabled.

    Args:
        message: Message to print
        args: Parsed arguments with verbose attribute
    """
    if hasattr(args, 'verbose') and args.verbose:
        colored_msg = colorize(f"[VERBOSE] {message}", Colors.GRAY, args)
        print(colored_msg, file=sys.stderr)


def print_debug(message, args):
    """Print debug message if debug mode is enabled.

    Args:
        message: Message to print
        args: Parsed arguments with debug attribute
    """
    if hasattr(args, 'debug') and args.debug:
        colored_msg = colorize(f"[DEBUG] {message}", Colors.CYAN, args)
        print(colored_msg, file=sys.stderr)


def get_exit_code(exception):
    """Map exception type to exit code.

    Args:
        exception: Exception instance

    Returns:
        Exit code integer
    """
    exc_type = type(exception).__name__

    if 'Connection' in exc_type or 'connection' in str(exception).lower():
        return EXIT_CONNECTION_ERROR
    elif 'NotImplementedError' in exc_type:
        return EXIT_NOT_IMPLEMENTED
    elif 'FileNotFoundError' in exc_type or 'No such file' in str(exception):
        return EXIT_FILE_NOT_FOUND
    elif 'Timeout' in exc_type or 'timeout' in str(exception).lower():
        return EXIT_TIMEOUT
    elif 'ValueError' in exc_type or 'Invalid' in str(exception):
        return EXIT_INVALID_ARGUMENTS
    else:
        return EXIT_GENERAL_ERROR


def handle_error(exception, args):
    """Handle and display error to user.

    Args:
        exception: Exception that occurred
        args: Parsed arguments
    """
    # Print error message
    print_error(str(exception), args)

    # Print verbose context if enabled
    if hasattr(args, 'verbose') and args.verbose:
        print_verbose(f"Exception type: {type(exception).__name__}", args)

    # Print stack trace if debug enabled
    if hasattr(args, 'debug') and args.debug:
        import traceback
        print_debug("Stack trace:", args)
        traceback.print_exc(file=sys.stderr)


def apply_env_vars(args):
    """Apply environment variables to arguments if not already set.

    Args:
        args: Parsed arguments namespace

    Returns:
        Modified args namespace
    """
    # BMC connection parameters
    if not args.ip and os.environ.get('BMC_HOST'):
        args.ip = os.environ.get('BMC_HOST')

    if not args.username and os.environ.get('BMC_USERNAME'):
        args.username = os.environ.get('BMC_USERNAME')

    if not args.password and os.environ.get('BMC_PASSWORD'):
        args.password = os.environ.get('BMC_PASSWORD')

    # Manufacturer override
    if hasattr(args, 'manufacturer') and not args.manufacturer and os.environ.get('BMC_MANUFACTURER'):
        args.manufacturer = os.environ.get('BMC_MANUFACTURER')

    # SSL verification
    if hasattr(args, 'insecure') and not args.insecure and os.environ.get('BMC_INSECURE'):
        args.insecure = os.environ.get('BMC_INSECURE').lower() in ('1', 'true', 'yes')

    return args


def validate_connection_args(args, required_fields=None):
    """Validate that required connection arguments are present.

    Args:
        args: Parsed arguments
        required_fields: List of required field names (default: ['ip', 'username', 'password'])

    Raises:
        ValueError: If required fields are missing
    """
    if required_fields is None:
        required_fields = ['ip', 'username', 'password']

    missing = []
    for field in required_fields:
        if not hasattr(args, field) or not getattr(args, field):
            missing.append(field)

    if missing:
        missing_str = ', '.join(f'--{f}' for f in missing)
        raise ValueError(f"Missing required arguments: {missing_str}. "
                        f"Provide via command line or environment variables "
                        f"(BMC_HOST, BMC_USERNAME, BMC_PASSWORD)")


def establish_redfish_connection(args):
    """Establish Redfish connection with error handling.

    Args:
        args: Parsed arguments with connection parameters

    Returns:
        Redfish instance

    Raises:
        ValueError: If connection parameters are invalid
        ConnectionError: If connection fails
    """
    from bmctools.redfish.redfish import Redfish

    validate_connection_args(args)

    print_verbose(f"Connecting to {args.ip}...", args)

    try:
        rf = Redfish(
            ip=args.ip,
            username=args.username,
            password=args.password,
            verify_ssl=not getattr(args, 'insecure', False),
            manufacturer=getattr(args, 'manufacturer', None)
        )

        if not getattr(args, 'insecure', False):
            print_verbose("SSL verification enabled", args)
        else:
            rf.api.disable_ssl_verification()
            print_verbose("SSL verification disabled", args)

        print_verbose(f"Connected successfully", args)
        print_verbose(f"Manufacturer: {rf.manufacturer}", args)
        print_verbose(f"System ID: {rf.system_id}", args)

        return rf
    except Exception as e:
        raise ConnectionError(f"Failed to connect to {args.ip}: {e}")


def establish_ipmi_connection(args):
    """Establish IPMI connection.

    Args:
        args: Parsed arguments with connection parameters

    Returns:
        IpmiTool instance

    Raises:
        ValueError: If connection parameters are invalid
    """
    from bmctools.ipmi.ipmitool import IpmiTool

    validate_connection_args(args)

    print_verbose(f"Creating IPMI connection to {args.ip}...", args)

    ipmi = IpmiTool(
        host=args.ip,
        username=args.username,
        password=args.password
    )

    print_verbose("IPMI connection created", args)
    return ipmi


def establish_racadm_connection(args):
    """Establish RACADM connection.

    Args:
        args: Parsed arguments with connection parameters

    Returns:
        Racadm instance

    Raises:
        ValueError: If connection parameters are invalid
    """
    from bmctools.racadm.racadm import Racadm

    validate_connection_args(args)

    print_verbose(f"Creating RACADM connection to {args.ip}...", args)

    racadm = Racadm(
        host=args.ip,
        username=args.username,
        password=args.password
    )

    print_verbose("RACADM connection created", args)
    return racadm
