#!/usr/bin/env python3
"""
monitor.py - Daily health report for Linux servers.

Collects system information, prints it to the terminal and saves it to
reports/server_report.txt so the Operations team does not have to log in
to every server and collect it by hand.

Only the Python standard library is used, so the script can be dropped on
any server with Python 3 installed - no pip install needed.
"""

import getpass
import os
import platform
import shutil
import socket
import time
from datetime import datetime

OS_RELEASE_FILE = "/etc/os-release"
PROC_STAT_FILE = "/proc/stat"
PROC_MEMINFO_FILE = "/proc/meminfo"
PROC_UPTIME_FILE = "/proc/uptime"

# Filesystem we report on. "/" is what the ops team cares about.
ROOT_FILESYSTEM = "/"

# How long we wait between the two /proc/stat samples.
CPU_SAMPLE_SECONDS = 1.0

GIB = 1024 ** 3

# Paths are resolved from the script location and not from the current
# working directory, so the report ends up in the right place also when
# the script is started from cron or from another folder.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
REPORT_FILE = os.path.join(REPORTS_DIR, "server_report.txt")

REPORT_WIDTH = 50


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


def get_disk_usage(path=ROOT_FILESYSTEM):
    """Return used / free space and the usage percentage for a filesystem."""
    usage = shutil.disk_usage(path)

    # df calculates Use% against (used + available) and not against the raw
    # size, because a few percent of the device is reserved for root.
    # We do the same so the numbers match `df -h`.
    denominator = usage.used + usage.free
    percent = 0.0
    if denominator:
        percent = round(usage.used / denominator * 100.0, 1)

    return {
        "filesystem": path,
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": percent,
    }


def get_ip_address():
    """Return the primary IPv4 address of this machine.

    A server can have several interfaces, so we ask the kernel which one it
    would use to reach the outside world. UDP means no packet is actually
    sent, the socket only gets a local address assigned.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        # No default route, e.g. an isolated host. Try the hostname instead.
        try:
            return socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            return "127.0.0.1"
    finally:
        sock.close()


def get_uptime():
    """Return how long the server has been running, e.g. '3 Days 5 Hours'."""
    with open(PROC_UPTIME_FILE, "r") as f:
        total_seconds = float(f.readline().split()[0])

    days = int(total_seconds // 86400)
    hours = int((total_seconds % 86400) // 3600)
    minutes = int((total_seconds % 3600) // 60)

    if days:
        return "{} Days {} Hours".format(days, hours)
    if hours:
        return "{} Hours {} Minutes".format(hours, minutes)
    return "{} Minutes".format(minutes)


def collect_system_info():
    """Run every collector once and return the result as a dictionary."""
    return {
        "hostname": get_hostname(),
        "user": get_current_user(),
        "date": get_datetime(),
        "os": get_operating_system(),
        "kernel": get_kernel_version(),
        "cpu": get_cpu_usage(),
        "memory": get_memory_usage(),
        "disk": get_disk_usage(),
        "ip": get_ip_address(),
        "uptime": get_uptime(),
    }


def build_report(info):
    """Render the collected information as the plain text report."""
    line = "=" * REPORT_WIDTH
    memory = info["memory"]
    disk = info["disk"]

    rows = [
        line,
        # rstrip so we do not leave trailing spaces after the title
        "SERVER HEALTH REPORT".center(REPORT_WIDTH).rstrip(),
        line,
        "",
        "Hostname         : {}".format(info["hostname"]),
        "Current User     : {}".format(info["user"]),
        "Date             : {}".format(info["date"]),
        "Operating System : {}".format(info["os"]),
        "Kernel           : {}".format(info["kernel"]),
        "CPU Usage        : {} %".format(info["cpu"]),
        "",
        "Memory Usage",
        "  Total          : {}".format(to_gb(memory["total"])),
        "  Used           : {}".format(to_gb(memory["used"])),
        "  Free           : {}".format(to_gb(memory["free"])),
        "  Usage          : {} %".format(memory["percent"]),
        "",
        "Disk Usage",
        "  Filesystem     : {}".format(disk["filesystem"]),
        "  Used           : {}".format(to_gb(disk["used"])),
        "  Available      : {}".format(to_gb(disk["free"])),
        "  Usage          : {} %".format(disk["percent"]),
        "",
        "IP Address       : {}".format(info["ip"]),
        "Uptime           : {}".format(info["uptime"]),
        "",
        line,
    ]
    return "\n".join(rows) + "\n"


def save_report(report, path=REPORT_FILE):
    """Write the report to disk and return the path it was written to."""
    # The reports folder is in git, but it can be missing if somebody only
    # copied monitor.py to a server, so create it when needed.
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w") as f:
        f.write(report)

    return path


def main():
    """Collect the data, print the report and save it to disk."""
    info = collect_system_info()
    report = build_report(info)

    # Same text on screen and in the file, no risk of the two drifting apart
    print(report, end="")

    path = save_report(report)
    print("Report saved to: {}".format(path))


if __name__ == "__main__":
    main()
