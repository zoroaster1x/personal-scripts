#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess
from pathlib import Path

def run_cmd(cmd, check=True):
    """Helper to run shell commands and print what's running."""
    cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
    print(f"\n[+] Running: {cmd_str}")
    return subprocess.run(cmd, check=check)

def main():
    # 1. Block running as root directly
    if os.geteuid() == 0:
        print("ERROR: Please run this script as your normal user, NOT with sudo.")
        print("AUR helpers (paru/yay) block root execution. The script will ask for your sudo password safely.")
        sys.exit(1)

    print("==========================================")
    print("   Starting MSI Arch/CachyOS Setup...     ")
    print("==========================================")

    # 2. Ask for sudo upfront and cache the credentials
    print("\n[!] Please enter your sudo password to begin the automated setup:")
    run_cmd(["sudo", "-v"])

    # 3. Detect the AUR Helper
    aur_helper = None
    if shutil.which("paru"):
        aur_helper = "paru"
    elif shutil.which("yay"):
        aur_helper = "yay"
    else:
        print("ERROR: Neither paru nor yay was found! Please install an AUR helper.")
        sys.exit(1)
        
    print(f"-> Found AUR helper: {aur_helper}")

    # 4. Define all packages
    packages =[
        # System & Hardware
        "msi-ec-dkms-git", "mcontrolcenter-bin", "ckb-next", "nvtop", "flatpak",
        
        # Utilities & CLI
        "7zip", "btop", "bun", "darkly-bin", "glances", "micro", "pandoc-cli", "ripgrep", "tree", "zip",
        "wl-clipboard", "xclip", "grim", "slurp", "scrcpy", "veracrypt", "yt-dlp",

        # Script Dependencies (required by scripts/ tools)
        "ffmpeg", "python-rich",

        # Virtualization & Networking
        "qemu-full", "libvirt", "virt-manager", "virt-viewer", "dnsmasq", "vde2", "bridge-utils", "iptables-nft",
        "mullvad-vpn",
        
        # Applications
        "alacritty", "audacity", "brave-bin", "converseen", "element-desktop", "handbrake",
        "inkscape", "jre-openjdk", "kdenlive", "obs-studio", "qbittorrent", "thunderbird",
        "qt6-tools-desktop", "kwin-effects-glass-git",
        
        # Media Control
        "mpv-mpris", "playerctl"
    ]

    # Prepare flags to accept Yes on everything and hide diffs
    install_cmd = [aur_helper, "-S", "--needed", "--noconfirm"]
    if aur_helper == "paru":
        install_cmd.append("--skipreview")
    elif aur_helper == "yay":
        install_cmd.extend(["--answerclean=All", "--answerdiff=None"])

    install_cmd.extend(packages)

    print("\n-> Installing System and AUR Packages (No prompts)...")
    try:
        run_cmd(install_cmd)
    except subprocess.CalledProcessError:
        print("\n[!] Warning: Some packages failed to install. Continuing with the rest of the setup...")

    # 5. Enable Required System Services & Groups
    print("\n-> Enabling system services (VPN, Keyboard, Libvirt)...")
    services =["mullvad-daemon", "ckb-next-daemon", "libvirtd"]
    for srv in services:
        run_cmd(["sudo", "systemctl", "enable", "--now", srv])

    print("-> Adding user to virtualization groups...")
    user = os.environ.get("USER")
    for group in ["libvirt", "kvm"]:
        run_cmd(["sudo", "usermod", "-aG", group, user])

    # 6. Install Flatpaks
    flatpaks =[
        "chat.simplex.simplex", "com.github.vikdevelop.timer", "com.rtosta.zapzap",
        "dev.deedles.Trayscale", "fr.arnaudmichel.launcherstudio", "hu.irl.cameractrls",
        "io.github.kolunmi.Bazaar", "io.github.mrvladus.List", "io.missioncenter.MissionCenter",
        "md.obsidian.Obsidian", "org.keepassxc.KeePassXC", "org.zotero.Zotero",
        "re.fossplant.vmlinux-to-elf", "us.zoom.Zoom"
    ]
    
    print("\n-> Setting up Flathub and Applications...")
    run_cmd(["flatpak", "remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
    run_cmd(["flatpak", "install", "-y", "flathub"] + flatpaks)

    # 7. Setup Local Scripts (from your `scripts/` directory)
    print("\n-> Setting up local bash/fish scripts...")
    home_dir = Path.home()
    local_bin = home_dir / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    
    # Path to the scripts folder in the same directory as this Python file
    repo_scripts_dir = Path(__file__).parent / "scripts"

    if repo_scripts_dir.exists() and repo_scripts_dir.is_dir():
        for script_path in repo_scripts_dir.iterdir():
            if script_path.is_file():
                dest_path = local_bin / script_path.name
                shutil.copy2(script_path, dest_path)
                dest_path.chmod(0o755) # Make executable (chmod +x)
                print(f"Copied & made executable: {dest_path}")
    else:
        print(f"[!] Warning: Scripts directory not found at {repo_scripts_dir}")

    # 8. Setup Fish Shell
    if shutil.which("fish"):
        print("\n-> Fish Shell Detected. Configuring environment...")
        
        # As seen in your history: fish_add_path ~/.local/bin
        print("Adding ~/.local/bin to fish path...")
        run_cmd(["fish", "-c", f"fish_add_path {local_bin}"])
        
        # Install sdkman-for-fish using fisher
        print("Installing sdkman-for-fish plugin...")
        try:
            run_cmd(["fish", "-c", "fisher install reitzig/sdkman-for-fish@v2.1.0"])
        except subprocess.CalledProcessError:
            print("[!] Warning: Failed to install fish plugin. Ensure 'fisher' is installed.")

    print("\n==========================================")
    print("   Setup Complete! Please reboot soon.    ")
    print("==========================================")

if __name__ == "__main__":
    main()