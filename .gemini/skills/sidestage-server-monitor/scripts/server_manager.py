import sys
import subprocess
import os
from pathlib import Path
import time
import signal
import json

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
        try:
            pid = int(pid_file.read_text())
            os.kill(pid, 0)
            print(f"Server is already running for campaign '{campaign_name}' (PID: {pid})")
            return
        except (OSError, ValueError):
            pid_file.unlink()

    print(f"Starting server for campaign '{campaign_name}' (reload={reload})...")
    
    # Use absolute path for poetry to ensure it's found
    cmd = ["poetry", "run", "server", campaign_name]
    if reload:
        cmd.append("--reload")

    with open(log_file, "a") as log:
        process = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setpgrp,
            env={**os.environ, "SIDESTAGE_CAMPAIGN": campaign_name}
        )
        pid_file.write_text(str(process.pid))
    
    print(f"Server started (PID: {process.pid}). Logs: {log_file}")

def stop(campaign_name):
    pid_file = get_pid_file(campaign_name)
    if not pid_file.exists():
        print(f"No server running for campaign '{campaign_name}'")
        return

    try:
        pid = int(pid_file.read_text())
        os.killpg(pid, signal.SIGTERM)
        print(f"Stopped server for campaign '{campaign_name}' (PID: {pid})")
    except (OSError, ValueError):
        print("Process already dead or PID invalid.")
    
    if pid_file.exists():
        pid_file.unlink()

def status(campaign_name):
    pid_file = get_pid_file(campaign_name)
    if not pid_file.exists():
        print(f"Server NOT running for campaign '{campaign_name}'")
        return False

    try:
        pid = int(pid_file.read_text())
        os.kill(pid, 0)
        print(f"Server is running for campaign '{campaign_name}' (PID: {pid})")
        return True
    except (OSError, ValueError):
        print(f"Server CRASHED or stopped unexpectedly (Stale PID: {pid if 'pid' in locals() else 'unknown'})")
        if pid_file.exists():
            pid_file.unlink()
        return False

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

def call(campaign_name, endpoint, method="GET", data=None, files=None):
    import requests
    url = f"http://localhost:8000{endpoint}"
    print(f"Calling {method} {url}...")
    try:
        if method == "GET":
            resp = requests.get(url, timeout=30)
        elif method == "POST":
            if files is not None:
                # Use data for form fields when files are present
                # Convert all values to strings for multipart/form-data
                form_data = {k: str(v) if not isinstance(v, bool) else str(v).lower() for k, v in data.items()} if data else {}
                resp = requests.post(url, data=form_data, files=files, timeout=60)
            else:
                resp = requests.post(url, json=data, timeout=60)
        else:
            print(f"Method {method} not supported")
            return

        if resp.status_code != 200:
            print(f"Error: Server returned status {resp.status_code}")
            print(resp.text)
            return

        try:
            print(json.dumps(resp.json(), indent=2))
        except json.JSONDecodeError:
            print("Raw response (not JSON):")
            print(resp.text)
            
    except requests.exceptions.Timeout:
        print(f"Error: Request to {endpoint} timed out.")
    except Exception as e:
        print(f"Error calling endpoint {endpoint}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python server_manager.py [start|stop|status|monitor|call] [campaign_name] [endpoint] [method] [data_json]")
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
    elif cmd == "call":
        if len(sys.argv) < 4:
            print("Usage: python server_manager.py call [campaign_name] [endpoint] [method] [data_json]")
            sys.exit(1)
        endpoint = sys.argv[3]
        method = sys.argv[4] if len(sys.argv) > 4 else "GET"
        data_str = sys.argv[5] if len(sys.argv) > 5 else None
        data = json.loads(data_str) if data_str else None
        
        # Special handling for agent runs which Agno expects as multipart/form-data
        if "runs" in endpoint and method == "POST":
            call(campaign, endpoint, method, data=data, files={})
        else:
            call(campaign, endpoint, method, data)
    else:
        print(f"Unknown command: {cmd}")
