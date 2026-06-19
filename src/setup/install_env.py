import os
import sys
import subprocess

def run_command(command: list, interactive: bool = False):
    """
    Run a system command.
    Args:
        command (list): The command to run.
        interactive (bool): Whether to run the command interactively.
    """
    try:
        if interactive:
            subprocess.run(command, check=True)
        else:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n>>> Error: Command '{' '.join(command)}' failed with exit code {e.returncode}.")
        return False

def install_dependencies():
    """
    Install the necessary dependencies for the application.
    """
    print(">>> Updating package lists...")
    if not run_command(["apt-get", "update"]):
        print(">>> Critical Error: Could not update apt-get. Exiting.")
        sys.exit(1)

    packages = [
        "python3-requests", 
        "python3-mysql.connector",
        "python3-dotenv",
        "wakeonlan"
    ]

    print("\n>>> Installing required packages...")
    for pkg in packages:
        print(f" -> Installing {pkg}...")
        if not run_command(["apt-get", "install", "-y", pkg]):
            print(f" -> Error: Failed to install '{pkg}'. Skipping...\n")
            continue # Skip the package and continue

    print("\n>>> All dependencies installed successfully.")

def install_fog():
    """
    Install or update the FOG Server.
    """
    print(">>> Installing / Updating FOG Server...")
    fog_dir = "/opt/fogproject"

    if not os.path.exists(fog_dir):
        print(" -> Installing FOG Server (this may take a while)...")
        if not run_command(["git", "clone", "https://github.com/FOGProject/fogproject.git", fog_dir]):
            print(">>> Error: Failed to install FOG Server.")
            sys.exit(1)
    else:
        print(" -> Updating FOG Server. Pulling latest changes...")
        if not run_command(["git", "-C", fog_dir, "pull"]):
            print(">>> Error: Failed to update FOG Server.")
            sys.exit(1)
    
    print("\n" + "="*50)
    print("STARTING FOG INSTALLER")
    print("="*50 + "\n")

    install_script = os.path.join(fog_dir, "bin", "installfog.sh")
    try:
        subprocess.run(["bash", install_script], cwd=os.path.join(fog_dir, "bin"), check=True)
    except subprocess.CalledProcessError as e:
        print(f">>> Error: FOG installation failed with exit code {e.returncode}.")
        sys.exit(1)

if __name__ == "__main__":
    if os.geteuid() != 0: # Check if the script is run as root (getuid() only exists on Linux and Unix systems)
        print(">>> ERROR: This setup script must be run as root (sudo).")
        sys.exit(1)        
    install_dependencies()
    install_fog()