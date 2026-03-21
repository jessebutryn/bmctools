import shutil
import os
from datetime import datetime

class DirectoryError(Exception):
    """
    Custom exception to throw directoryerror
    """

    pass

def is_command(cmd: str) -> bool:
    """Check whether a command is available on the current system PATH.

    Args:
        cmd: Command name to look up (e.g. ``'racadm'``).

    Returns:
        ``True`` if the command is found on PATH.

    Raises:
        FileNotFoundError: If the command is not found.
    """
    if shutil.which(cmd) is not None:
        return True
    else:
        raise FileNotFoundError(
            f"The command '{cmd}' was not found.  Please ensure this is run from the platops-toolbox"
        )

def is_dir_writeable(dir: str) -> bool:
    """Test whether a directory exists and is writeable.

    Args:
        dir: Absolute or relative path to the directory.

    Returns:
        ``True`` if the directory exists and is writeable.

    Raises:
        DirectoryError: If the directory does not exist or is not writeable.
    """
    if os.path.exists(dir):
        if os.access(dir, os.W_OK):
            return True
        else:
            raise DirectoryError(f"The directory '{dir}' is not writeable")
    else:
        raise DirectoryError(f"The directory '{dir}' does not exist")


def is_older_than_unit(given_time: str, age: int, unit: str) -> bool:
    """Check whether a timestamp is older than the given duration.

    Args:
        given_time: Datetime string in ``'%Y-%m-%d %H:%M:%S'`` format.
        age: Numeric age threshold.
        unit: Time unit character — ``'d'`` (days), ``'h'`` (hours),
              ``'m'`` (minutes), or ``'s'`` (seconds).

    Returns:
        ``True`` if *given_time* is older than ``age`` *unit*\\s ago,
        ``False`` otherwise.
    """
    time_since_now = datetime.now() - datetime.strptime(given_time, "%Y-%m-%d %H:%M:%S")
    if unit == "d":
        if time_since_now.total_seconds() // 86400 >= age:
            return True
    elif unit == "h":
        if time_since_now.total_seconds() // 3600 >= age:
            return True
    elif unit == "m":
        if time_since_now.total_seconds() // 60 >= age:
            return True
    elif unit == "s":
        if time_since_now.total_seconds() >= age:
            return True