import sys
import subprocess
import os
from pathlib import Path
import time
import signal

def get_campaign_dir(campaign_name):
    return Path.home() / ".sidestage" / campaign_name

def get_pid_file(campaign_name):
    return get_campaign_dir(campaign_name) / "server.pid"

def get_log_file(campaign_name):
    return get_campaign_dir(campaign_name) / "server.log"

def start(campaign_name, reload=False):
    campaign_dir = get_campaign_dir(campaign_name)
    campaign_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = get_log_file(campaign_name)
    pid_file = get_pid_file(campaign_name)
    
    if pid_file.exists():
        pid = int(pid_file.read_text())
        try:
            os.kill(pid, 0)
            print(f"Server is already running for campaign '{campaign_name}' (PID: {pid})")
            return
        except OSError:
            pid_file.unlink()

    print(f"Starting server for campaign '{campaign_name}' (reload={reload})...")
    
    cmd = ["poetry", "run", "server", campaign_name]
    if reload:
        cmd.append("--reload")

    with open(log_file, "a") as log:
        process = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setpgrp
        )
        pid_file.write_text(str(process.pid))
    
    print(f"Server started (PID: {process.pid}). Logs: {log_file}")

def stop(campaign_name):
    pid_file = get_pid_file(campaign_name)
    if not pid_file.exists():
        print(f"No server running for campaign '{campaign_name}'")
        return

    pid = int(pid_file.read_text())
    try:
        os.killpg(pid, signal.SIGTERM)
        print(f"Stopped server for campaign '{campaign_name}' (PID: {pid})")
    except OSError:
        print(f"Process {pid} already dead.")
    
    pid_file.unlink()

def status(campaign_name):
    pid_file = get_pid_file(campaign_name)
    if not pid_file.exists():
        print(f"Server NOT running for campaign '{campaign_name}'")
        return

    pid = int(pid_file.read_text())
    try:
        os.kill(pid, 0)
        print(f"Server is running for campaign '{campaign_name}' (PID: {pid})")
    except OSError:
        print(f"Server CRASHED or stopped unexpectedly (Stale PID: {pid})")
        pid_file.unlink()

def monitor(campaign_name, lines=20):
    log_file = get_log_file(campaign_name)
    if not log_file.exists():
        print(f"No log file found for campaign '{campaign_name}'")
        return

    print(f"--- Latest logs for '{campaign_name}' ---")
    try:
        output = subprocess.check_output(["tail", "-n", str(lines), str(log_file)], text=True)
        print(output)
        
        has_error = "ERROR" in output or "Exception" in output or "Traceback" in output
        has_warning = "WARNING" in output
        
        if has_error:
            print("CRITICAL: Errors detected in the logs!")
            sys.exit(2)
        if has_warning:
            print("WARNING: Warnings detected in the logs.")
            sys.exit(3)
            
    except subprocess.CalledProcessError:
        print("Error reading log file.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python server_manager.py [start|stop|status|monitor] [campaign_name]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    campaign = sys.argv[2]
    
    if cmd == "start":
        do_reload = "--reload" in sys.argv
        start(campaign, reload=do_reload)
    elif cmd == "stop":
        stop(campaign)
    elif cmd == "status":
        status(campaign)
    elif cmd == "monitor":
        monitor(campaign)
    else:
        print(f"Unknown command: {cmd}")
