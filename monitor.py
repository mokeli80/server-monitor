#!/usr/bin/env python3
"""
monitor.py - Daily health report for Linux servers.

Collects basic system information and prints it to the terminal.
"""

import getpass
import os
import platform
import socket
from datetime import datetime

OS_RELEASE_FILE = "/etc/os-release"


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


def get_operating_system():
    """Return the distribution name, e.g. 'Ubuntu 24.04.4 LTS'.

    /etc/os-release is the standard file on every modern Linux distro,
    so we read PRETTY_NAME from it instead of shelling out to lsb_release.
    """
    try:
        with open(OS_RELEASE_FILE, "r") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    # Not a Linux box, or the file is missing
    return platform.system()


def get_kernel_version():
    """Return the running kernel version, e.g. '6.8.0-51-generic'."""
    return platform.release()


def main():
    print("Hostname         : {}".format(get_hostname()))
    print("Current User     : {}".format(get_current_user()))
    print("Date             : {}".format(get_datetime()))
    print("Operating System : {}".format(get_operating_system()))
    print("Kernel           : {}".format(get_kernel_version()))


if __name__ == "__main__":
    main()
