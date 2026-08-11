#!/usr/bin/env python3
"""
monitor.py - Daily health report for Linux servers.

Collects basic system information and prints it to the terminal.
"""

import getpass
import os
import socket
from datetime import datetime


def get_hostname():
    """Return the hostname of the machine."""
    return socket.gethostname()


def get_current_user():
    """Return the user the script is running as."""
    try:
        return getpass.getuser()
    except Exception:
        # getpass needs a working password database, fall back to the env
        return os.environ.get("USER", "unknown")


def get_datetime():
    """Return the current local date and time as YYYY-MM-DD HH:MM."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def main():
    print("Hostname     : {}".format(get_hostname()))
    print("Current User : {}".format(get_current_user()))
    print("Date         : {}".format(get_datetime()))


if __name__ == "__main__":
    main()
