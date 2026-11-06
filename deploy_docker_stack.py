import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import json
import urllib.request
import socket
from pathlib import Path
import paramiko

PI_CANDIDATES = ["192.168.1.107", "192.168.1.108", "pi.local", "raspberrypi.local"]
PORT = 22

FILES_TO_SYNC = [
    ("backend/vpn_monitor.py", "backend/vpn_monitor.py"),
    ("backend/server.py", "backend/server.py"),
    ("backend/version.py", "backend/version.py"),
    ("backend/optimizer.py", "backend/optimizer.py"),
    ("backend/docker_monitor.py", "backend/docker_monitor.py"),
    ("backend/utils.py", "backend/utils.py"),
    ("frontend/index.html", "frontend/index.html"),
    ("frontend/css/style.css", "frontend/css/style.css"),
    ("frontend/js/app.js", "frontend/js/app.js"),
    ("homepage/config/docker.yaml", "homepage/config/docker.yaml"),
    ("homepage/config/settings.yaml", "homepage/config/settings.yaml"),
    ("homepage/config/widgets.yaml", "homepage/config/widgets.yaml"),
    ("homepage/config/services.yaml", "homepage/config/services.yaml"),
    ("Dockerfile", "Dockerfile"),
    ("docker-compose.yml", "docker-compose.yml"),
    ("requirements.txt", "requirements.txt"),
    ("run.py", "run.py"),
    ("install_pi.sh", "install_pi.sh"),
    ("setup_docker_stack.sh", "setup_docker_stack.sh"),
    ("portal/index.html", "portal/index.html"),
    ("portal/nginx.conf", "portal/nginx.conf"),
    ("README.md", "README.md"),
]

def find_active_host():
    for h in PI_CANDIDATES:
        try:
            s = socket.create_connection((h, PORT), timeout=1.5)
            s.close()
            return h
        except Exception:
            continue
    return "192.168.1.107"

def check_endpoint(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def deploy_docker_stack(username, password, host=None):
    if not host:
        host = find_active_host()

    print(f"[*] Target Raspberry Pi: {host}:{PORT}")
    print(f"[*] Connecting as '{username}'...")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(
            hostname=host,
            port=PORT,
            username=username,
            password=password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False
        )
    except Exception as e:
        print(f"[!] SSH Connection failed: {e}")
        return False

    print("[+] SSH connection established successfully!")
    
    # Locate remote NetPulse directory
    cmd_find = (
        "for d in ~/netpulse ~/NetOptimizer ~/NetPulse /home/$USER/netpulse /home/$USER/NetOptimizer; do "
        "if [ -d \"$d\" ]; then echo \"$d\"; break; fi; done"
    )
    stdin, stdout, stderr = client.exec_command(cmd_find)
    remote_dir = stdout.read().decode().strip()
    if not remote_dir:
        remote_dir = f"/home/{username}/netpulse"
        client.exec_command(f"mkdir -p '{remote_dir}'")

    print(f"[+] Remote NetPulse directory: {remote_dir}")

    # SFTP upload
    print("[*] Syncing updated workspace files and deployment scripts...")
    sftp = client.open_sftp()
    base_local = Path(__file__).resolve().parent

    for rel_src, rel_dst in FILES_TO_SYNC:
        local_path = base_local / rel_src
        if not local_path.exists():
            continue
        remote_path = f"{remote_dir}/{rel_dst}".replace("//", "/")
        remote_parent = str(Path(remote_path).parent).replace("\\", "/")
        try:
            client.exec_command(f"mkdir -p '{remote_parent}'")
        except Exception:
            pass
        sftp.put(str(local_path), remote_path)

    sftp.close()
    print("[+] Files uploaded successfully!")

    # Set execute permissions
    client.exec_command(f"chmod +x '{remote_dir}/setup_docker_stack.sh' '{remote_dir}/install_pi.sh'")

    # Execute setup_docker_stack.sh
    print("\n[*] Launching Docker Stack setup (stopping bare-metal NetPulse, building NetPulse container, & launching God's Eye View)...")
    print("----------------------------------------------------------------------")
    
    # We pass the sudo password to validate sudo credentials, then run setup_docker_stack.sh as user
    exec_cmd = f"echo '{password}' | sudo -S -v && cd '{remote_dir}' && bash setup_docker_stack.sh"
    stdin, stdout, stderr = client.exec_command(exec_cmd, get_pty=True)
    
    for line in iter(stdout.readline, ""):
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            sys.stdout.write(line.encode("ascii", errors="replace").decode("ascii"))
            sys.stdout.flush()

    exit_code = stdout.channel.recv_exit_status()
    print(f"\n[*] Remote deployment script exited with code: {exit_code}")

    print("----------------------------------------------------------------------")
    print("[*] Inspecting running Docker containers on Raspberry Pi...")
    stdin, stdout, stderr = client.exec_command("sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    print(stdout.read().decode())

    client.close()

    print("[*] Verifying HTTP endpoints over local network...")
    time.sleep(3)

    portal_url = f"http://{host}"
    netpulse_url = f"http://{host}:8765/api/system-health"
    gev_url = f"http://{host}:4173"
    pihole_url = f"http://{host}:8088/admin"
    home_url = f"http://{host}:3000"

    print(f"  - Sentry Hub Portal ({portal_url}): {'ONLINE' if check_endpoint(portal_url) else 'INITIALIZING / CHECK BROWSER'}")
    print(f"  - NetPulse Pro ({netpulse_url}): {'ONLINE' if check_endpoint(netpulse_url) else 'INITIALIZING / CHECK BROWSER'}")
    print(f"  - God's Eye View ({gev_url}): {'ONLINE' if check_endpoint(gev_url) else 'INITIALIZING / CHECK BROWSER'}")
    print(f"  - Pi-hole + Unbound ({pihole_url}): {'ONLINE' if check_endpoint(pihole_url) else 'INITIALIZING / CHECK BROWSER'}")
    print(f"  - Homepage Dashboard ({home_url}): {'ONLINE' if check_endpoint(home_url) else 'INITIALIZING / CHECK BROWSER'}")

    print("\n[SUCCESS] Deployment script finished.")
    return True

def load_env():
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        except Exception:
            pass

if __name__ == "__main__":
    load_env()
    user = sys.argv[1] if len(sys.argv) > 1 else os.getenv("PI_USER", "gabriel")
    pwd = sys.argv[2] if len(sys.argv) > 2 else os.getenv("PI_PASSWORD")
    h = sys.argv[3] if len(sys.argv) > 3 else os.getenv("PI_HOST")

    if not pwd and sys.stdin.isatty():
        import getpass
        try:
            pwd = getpass.getpass(f"Enter SSH password for {user}@{h or 'Pi'}: ")
        except Exception:
            pass

    if user and pwd:
        deploy_docker_stack(user, pwd, h)
    else:
        print("Usage: python deploy_docker_stack.py [username] [password] [host]")
        print("   or: Set PI_USER and PI_PASSWORD environment variables")
