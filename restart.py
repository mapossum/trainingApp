"""
restart.py  --  Kill and restart all annotation apps + Cloudflare tunnel.

Usage:
    python restart.py
"""

import subprocess
import time
import sys
import os

# ── Configuration ─────────────────────────────────────────────────────────────

PYTHON = r"C:\Users\georg\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl\python.exe"
CLOUDFLARED = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
APP_DIR = os.path.dirname(os.path.abspath(__file__))

APPS = [
    {"data": "data_seagrass",    "port": 5000},
    {"data": "data",             "port": 5001},
    {"data": "data_conch",       "port": 5003},
    {"data": "data_phragmites",  "port": 5007},
]

STARTUP_WAIT = 15   # seconds to wait before checking health
LOG_LINES    = 3    # tail lines to show per app

# ──────────────────────────────────────────────────────────────────────────────


def kill_all():
    print("Killing existing processes...")

    # Kill python.exe processes except this script itself
    current_pid = os.getpid()
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        parts = line.replace('"', '').split(',')
        if len(parts) >= 2:
            try:
                pid = int(parts[1].strip())
                if pid != current_pid:
                    r = subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True)
                    msg = r.stdout.strip()
                    if msg:
                        print(f"  {msg}")
            except ValueError:
                pass

    # Kill cloudflared
    result = subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.strip():
            print(f"  {line.strip()}")

    time.sleep(2)


def start_apps():
    print("\nStarting annotation apps...")
    procs = []
    for app in APPS:
        log_path = os.path.join(os.environ.get("TEMP", "."), f"app_{app['port']}.log")
        with open(log_path, "w") as log:
            proc = subprocess.Popen(
                [PYTHON, "-u", "app.py", "--data", app["data"], "--port", str(app["port"])],
                cwd=APP_DIR,
                stdout=log,
                stderr=log,
            )
        print(f"  port {app['port']}  ({app['data']})  PID {proc.pid}  log -> {log_path}")
        procs.append((app, log_path, proc))
    return procs


def start_tunnel():
    print("\nStarting Cloudflare tunnel...")
    log_path = os.path.join(os.environ.get("TEMP", "."), "cloudflared.log")
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [CLOUDFLARED, "tunnel", "run"],
            stdout=log,
            stderr=log,
        )
    print(f"  PID {proc.pid}  log -> {log_path}")
    return log_path, proc


def tail(path, n=3):
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]).rstrip()
    except Exception:
        return "(log not readable)"


def check_health(app_procs, tunnel_log):
    print(f"\nWaiting {STARTUP_WAIT}s for startup...")
    time.sleep(STARTUP_WAIT)

    print("\n-- App status --")
    all_ok = True
    for app, log_path, proc in app_procs:
        alive = proc.poll() is None
        status = "UP" if alive else "EXITED"
        if not alive:
            all_ok = False
        print(f"  :{app['port']} ({app['data']})  [{status}]")
        snippet = tail(log_path, LOG_LINES)
        for line in snippet.splitlines():
            print(f"    {line}")

    print("\n-- Tunnel status --")
    snippet = tail(tunnel_log, LOG_LINES)
    connected = "Registered tunnel connection" in snippet
    print(f"  {'CONNECTED' if connected else 'NOT CONNECTED'}")
    for line in snippet.splitlines():
        print(f"  {line}")

    print()
    if all_ok and connected:
        print("All services running.")
    else:
        print("WARNING: one or more services did not start correctly. Check logs above.")


def main():
    kill_all()
    app_procs = start_apps()
    tunnel_log, _ = start_tunnel()
    check_health(app_procs, tunnel_log)


if __name__ == "__main__":
    main()
