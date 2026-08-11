#!/usr/bin/env python3
"""
monitor.py - Daily health report for Linux servers.

Collects basic system information and prints it to the terminal.
"""

import getpass
import os
import platform
import socket
import time
from datetime import datetime

OS_RELEASE_FILE = "/etc/os-release"
PROC_STAT_FILE = "/proc/stat"
PROC_MEMINFO_FILE = "/proc/meminfo"

# How long we wait between the two /proc/stat samples.
CPU_SAMPLE_SECONDS = 1.0

GIB = 1024 ** 3


def to_gb(num_bytes):
    """Format a byte count as a human readable GB string."""
    return "{:.1f} GB".format(num_bytes / GIB)


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


def _read_cpu_times():
    """Return (total_jiffies, idle_jiffies) from the aggregated 'cpu' line."""
    with open(PROC_STAT_FILE, "r") as f:
        fields = f.readline().split()

    # fields[0] is the literal string "cpu", the rest are counters:
    # user nice system idle iowait irq softirq steal guest guest_nice
    values = [int(v) for v in fields[1:]]
    idle = values[3] + values[4]  # idle + iowait
    return sum(values), idle


def get_cpu_usage():
    """Return the CPU usage in percent.

    /proc/stat holds counters since boot, so a single read would only give
    the average since the machine started. We take two samples one second
    apart and compare them to get the usage *right now*.
    """
    total_before, idle_before = _read_cpu_times()
    time.sleep(CPU_SAMPLE_SECONDS)
    total_after, idle_after = _read_cpu_times()

    total_delta = total_after - total_before
    idle_delta = idle_after - idle_before
    if total_delta <= 0:
        return 0.0

    usage = (1.0 - idle_delta / total_delta) * 100.0
    # Clamp, counters can wrap around on very long running servers
    return round(min(max(usage, 0.0), 100.0), 1)


def _read_meminfo():
    """Return /proc/meminfo as a dict of {key: bytes}."""
    memory = {}
    with open(PROC_MEMINFO_FILE, "r") as f:
        for line in f:
            key, _, rest = line.partition(":")
            parts = rest.split()
            if parts:
                # /proc/meminfo reports kB, convert to bytes
                memory[key] = int(parts[0]) * 1024
    return memory


def get_memory_usage():
    """Return total / used / free RAM in bytes plus the usage percentage.

    'Used' is MemTotal - MemAvailable. MemFree alone is misleading because
    Linux keeps cache and buffers in RAM and frees them on demand.
    """
    memory = _read_meminfo()
    total = memory.get("MemTotal", 0)
    available = memory.get("MemAvailable", memory.get("MemFree", 0))
    used = total - available
    percent = round(used / total * 100.0, 1) if total else 0.0

    return {
        "total": total,
        "used": used,
        "free": available,
        "percent": percent,
    }


def main():
    memory = get_memory_usage()

    print("Hostname         : {}".format(get_hostname()))
    print("Current User     : {}".format(get_current_user()))
    print("Date             : {}".format(get_datetime()))
    print("Operating System : {}".format(get_operating_system()))
    print("Kernel           : {}".format(get_kernel_version()))
    print("CPU Usage        : {} %".format(get_cpu_usage()))
    print("")
    print("Memory Usage")
    print("  Total          : {}".format(to_gb(memory["total"])))
    print("  Used           : {}".format(to_gb(memory["used"])))
    print("  Free           : {}".format(to_gb(memory["free"])))
    print("  Usage          : {} %".format(memory["percent"]))


if __name__ == "__main__":
    main()
