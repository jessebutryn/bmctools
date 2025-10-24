import shutil
import os
from datetime import datetime

class DirectoryError(Exception):
    """
    Custom exception to throw directoryerror
    """

    pass

def is_command(cmd: str) -> bool:
    """
    is_command(cmd: str)
        Checks if a given command is in the PATH on the current system.
    """
    if shutil.which(cmd) is not None:
        return True
    else:
        raise FileNotFoundError(
            f"The command '{cmd}' was not found.  Please ensure this is run from the platops-toolbox"
        )

def is_dir_writeable(dir: str) -> bool:
    """
    Function to test whether or not a directory exists and is writeable.

    Sample Usage:
    if is_dir_writeable(dir):
        do_thing()
    """
    if os.path.exists(dir):
        if os.access(dir, os.W_OK):
            return True
        else:
            raise DirectoryError(f"The directory '{dir}' is not writeable")
    else:
        raise DirectoryError(f"The directory '{dir}' does not exist")


def is_older_than_unit(given_time: str, age: int, unit: str):
    """
    Returns True if given time is older than given unit of time e.g is_older_than_unit(time, 30, 'd').
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