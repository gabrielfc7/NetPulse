import os
import sys
import time
import json
import urllib.request
from pathlib import Path
import paramiko

PI_HOSTS = ["192.168.1.108", "192.168.1.107", "pi.local"]
PORT = 22

FILES_TO_SYNC = [
    ("backend/vpn_monitor.py", "backend/vpn_monitor.py"),
    ("backend/server.py", "backend/server.py"),
    ("backend/version.py", "backend/version.py"),
    ("frontend/index.html", "frontend/index.html"),
    ("frontend/css/style.css", "frontend/css/style.css"),
    ("frontend/js/app.js", "frontend/js/app.js"),
    ("README.md", "README.md"),
]

def check_live_api(host="192.168.1.108", port=8765):
    try:
        url = f"http://{host}:{port}/api/version"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return data.get("current_version")
    except Exception:
        return None

def deploy_to_pi(username, password, host="192.168.1.108"):
    print(f"[*] Connecting to Raspberry Pi at {host}:22 as user '{username}'...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(
            hostname=host,
            port=PORT,
            username=username,
            password=password,
            timeout=8,
            look_for_keys=True
        )
    except Exception as e:
        print(f"[!] SSH Connection failed: {e}")
        return False

    print("[+] SSH connection established successfully!")
    
    # Locate NetPulse directory on remote Pi
    stdin, stdout, stderr = client.exec_command(
        "for d in ~/netpulse ~/NetOptimizer ~/NetPulse /home/$USER/netpulse /home/$USER/NetOptimizer; do "
        "if [ -f \"$d/backend/server.py\" ]; then echo \"$d\"; break; fi; done"
    )
    remote_dir = stdout.read().decode().strip()
    
    if not remote_dir:
        # Fallback to searching
        stdin, stdout, stderr = client.exec_command("find ~ -name 'server.py' 2>/dev/null | grep 'backend/server.py' | head -n 1")
        found = stdout.read().decode().strip()
        if found:
            remote_dir = str(Path(found).parent.parent).replace("\\", "/")
        else:
            remote_dir = "~/netpulse"

    print(f"[+] Found remote NetPulse directory: {remote_dir}")

    # Transfer updated files via SFTP
    print("[*] Uploading v2.4.0 updated files via SFTP...")
    sftp = client.open_sftp()
    
    base_local = Path(__file__).resolve().parent

    for rel_src, rel_dst in FILES_TO_SYNC:
        local_path = base_local / rel_src
        remote_path = f"{remote_dir}/{rel_dst}".replace("//", "/")
        
        # Ensure remote parent directory exists
        remote_parent = str(Path(remote_path).parent).replace("\\", "/")
        try:
            client.exec_command(f"mkdir -p '{remote_parent}'")
        except Exception:
            pass
            
        print(f"    -> Uploading {rel_src} to {remote_path}...")
        sftp.put(str(local_path), remote_path)

    sftp.close()
    print("[+] All files uploaded successfully!")

    # Restart NetPulse on Pi
    print("[*] Restarting NetPulse service on Raspberry Pi...")
    # 1. Try systemctl
    client.exec_command(f"sudo systemctl restart netpulse 2>/dev/null || true")
    
    # 2. Check if netpulse is running via nohup/python
    stdin, stdout, stderr = client.exec_command("pgrep -f 'run.py' || pgrep -f 'backend.server'")
    pids = stdout.read().decode().strip().split()
    
    if pids:
        print(f"[*] Found running Python NetPulse PIDs: {pids}. Sending restart signal...")
        client.exec_command(f"kill {' '.join(pids)} 2>/dev/null || true")
        time.sleep(1.5)
        # Re-launch
        client.exec_command(f"cd '{remote_dir}' && nohup python3 run.py > netpulse.log 2>&1 &")
    else:
        # Launch if not running
        client.exec_command(f"cd '{remote_dir}' && nohup python3 run.py > netpulse.log 2>&1 &")

    print("[*] Waiting for NetPulse to initialize...")
    time.sleep(3)

    client.close()

    # Verify new version via HTTP
    for i in range(8):
        v = check_live_api(host)
        if v:
            print(f"[SUCCESS] Raspberry Pi NetPulse is live running version: v{v}!")
            return True
        time.sleep(1)

    print("[!] Service restarted, but API response check timed out. Please verify http://192.168.1.108:8765")
    return True

if __name__ == "__main__":
    user = sys.argv[1] if len(sys.argv) > 1 else os.getenv("PI_USER", "gabs")
    pwd = sys.argv[2] if len(sys.argv) > 2 else os.getenv("PI_PASSWORD")
    host = sys.argv[3] if len(sys.argv) > 3 else os.getenv("PI_HOST", "192.168.1.108")

    if not pwd and sys.stdin.isatty():
        import getpass
        try:
            pwd = getpass.getpass(f"Enter SSH password for {user}@{host}: ")
        except Exception:
            pass

    if user and pwd:
        deploy_to_pi(user, pwd, host)
    else:
        print("Usage: python deploy_pi.py <username> <password> [host]")
        print("   or: Set PI_USER and PI_PASSWORD environment variables")
