#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VizR Launcher - Windows 실행 프로그램
사용자가 더블클릭하면 VizR을 자동으로 실행합니다.
"""

import subprocess
import time
import webbrowser
import os
import sys
import tkinter as tk
from tkinter import messagebox, filedialog
import requests
from pathlib import Path
import threading
import json
from datetime import datetime
import ctypes
from ctypes import wintypes

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("⚠️ Warning: pystray not available. System tray icon will be disabled.")

# Toast notifications are not used anymore (replaced with console logging + pystray.notify)

class ProgressWindow:
    """Modern splash screen without title bar"""
    def __init__(self):
        self.root = tk.Tk()

        # Remove title bar
        self.root.overrideredirect(True)

        # Set window size
        window_width = 400
        window_height = 300

        # Center window on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Make window stay on top
        self.root.attributes('-topmost', True)

        # Main container with border
        main_frame = tk.Frame(
            self.root,
            bg="white",
            highlightbackground="#0066CC",
            highlightthickness=2
        )
        main_frame.pack(fill="both", expand=True)

        # Logo/Image placeholder (upper part)
        logo_frame = tk.Frame(main_frame, bg="white", height=200)
        logo_frame.pack(fill="x", pady=20)
        logo_frame.pack_propagate(False)

        # Try to load VizR logo image
        logo_loaded = False
        if PIL_AVAILABLE:
            # Get resource path (works for both development and PyInstaller)
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                base_path = sys._MEIPASS
            else:
                # Running as script
                base_path = os.path.dirname(__file__)

            logo_path = os.path.join(base_path, "vizr_logo.png")
            if os.path.exists(logo_path):
                try:
                    # Load and resize image
                    img = Image.open(logo_path)
                    img = img.resize((150, 150), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)

                    logo_label = tk.Label(
                        logo_frame,
                        image=photo,
                        bg="white"
                    )
                    logo_label.image = photo  # Keep reference
                    logo_label.pack(expand=True)
                    logo_loaded = True
                except Exception:
                    pass

        # If no image loaded, show text placeholder
        if not logo_loaded:
            logo_label = tk.Label(
                logo_frame,
                text="VizR",
                font=("Segoe UI", 48, "bold"),
                fg="#0066CC",
                bg="white"
            )
            logo_label.pack(expand=True)

            # Subtitle
            subtitle_label = tk.Label(
                logo_frame,
                text="RNA-Seq Analysis Platform",
                font=("Segoe UI", 10),
                fg="#666666",
                bg="white"
            )
            subtitle_label.place(relx=0.5, rely=0.75, anchor="center")

        # Status message (lower part)
        status_frame = tk.Frame(main_frame, bg="white")
        status_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.status_label = tk.Label(
            status_frame,
            text="Starting VizR...",
            font=("Segoe UI", 10),
            fg="#333333",
            bg="white"
        )
        self.status_label.pack()

        # Show window immediately
        self.root.update()

    def update_status(self, status, detail=""):
        """Update status message"""
        if detail:
            message = f"{status}\n{detail}"
        else:
            message = status
        self.status_label.config(text=message)
        self.root.update()

    def update_progress(self, current, total):
        """Update progress (not displayed in splash screen)"""
        # Progress is shown in status message instead
        pass

    def close(self):
        """Close window"""
        self.root.destroy()


class VizRLauncher:
    def __init__(self):
        self.container_name = "vizr"
        self.image_name = "hjung200x/vizr:latest"
        self.port = 5001
        self.vizr_path = None
        self.progress_window = None

    def convert_windows_path_to_docker(self, windows_path: str):
        """Convert Windows path to Docker volume format (supports UNC)."""
        path = windows_path.replace("\\", "/")

        # UNC 경로 (\\server\share) → //server/share
        if path.startswith("//"):
            return path

        # 드라이브 문자 경로 (C:/path → /c/path)
        if len(path) > 1 and path[1] == ":":
            return f"/{path[0].lower()}{path[2:]}"

        return path

    def check_docker_running(self):
        """Check if Docker Desktop is running"""
        try:
            # Use 'docker ps' instead of 'docker info' - much faster and lighter
            result = subprocess.run(
                ["docker", "ps"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace invalid characters
                timeout=3,  # Reduced timeout since 'docker ps' is faster than 'docker info'
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            # Docker daemon is not ready yet
            return False
        except Exception:
            # Docker command not found or other error
            return False

    def check_container_running(self):
        """Check if VizR container is already running"""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={self.container_name}", "--format", "{{.Names}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace invalid characters
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            return self.container_name in result.stdout
        except Exception:
            return False

    def start_docker_desktop(self):
        """Auto-start Docker Desktop (Tray Icon mode)"""
        # Docker Desktop path on Windows
        docker_desktop_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"

        if not os.path.exists(docker_desktop_path):
            return False

        # Start as tray icon (hide UI window)
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        subprocess.Popen([docker_desktop_path, "--openui=false"], creationflags=creationflags)

        # Wait for Docker daemon to be ready (max 120 seconds for first-time startup)
        for i in range(120):
            if self.check_docker_running():
                return True

            # Update progress every 5 seconds
            if i % 5 == 0:
                self.progress_window.update_status(
                    "Starting Docker Desktop...",
                    f"Waiting for Docker daemon... ({i}/120s)"
                )

            time.sleep(1)

        return False

    def get_vizr_path(self):
        """
        Get VIZR_PATH with priority:
        1. Config file (.vizr_config.json)
        2. Environment variable (VIZR_PATH)
        3. Error → Show Setup guide
        """
        # 1. Try reading from config file first
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            exe_dir = os.path.dirname(sys.executable)
        else:
            # Running as script (development)
            exe_dir = os.path.dirname(__file__)

        config_file = os.path.join(exe_dir, '.vizr_config.json')

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    vizr_path = config.get('vizr_path')

                    if vizr_path:
                        # Create directory if it doesn't exist
                        print(f"✅ Loaded VIZR_PATH from config: {vizr_path}")
                        Path(vizr_path).mkdir(parents=True, exist_ok=True)
                        self.vizr_path = vizr_path
                        return vizr_path
                    else:
                        print(f"⚠️ Config file exists but vizr_path is empty")
            except Exception as e:
                print(f"⚠️ Failed to read config file: {e}")

        # 2. Try environment variable
        vizr_path = os.environ.get("VIZR_PATH")
        if vizr_path:
            print(f"✅ Loaded VIZR_PATH from environment variable: {vizr_path}")
            Path(vizr_path).mkdir(parents=True, exist_ok=True)
            self.vizr_path = vizr_path
            return vizr_path

        # 3. No config file and no environment variable → Show Setup guide
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        messagebox.showerror(
            "VizR Configuration Missing",
            "VizR configuration file not found.\n\n"
            "Please run VizR_Setup.exe to install VizR properly.\n\n"
            "Setup will create the configuration file automatically.\n\n"
            "If you already installed VizR, the configuration file may have been deleted.\n"
            "Please reinstall VizR using VizR_Setup.exe.",
            parent=root
        )

        root.destroy()
        sys.exit(1)

    def stop_existing_container(self):
        """Remove existing stopped VizR container"""
        try:
            # Remove stopped container (running containers are skipped by check_container_running)
            subprocess.run(
                ["docker", "rm", self.container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace invalid characters
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
        except Exception:
            pass

    def stop_container(self):
        """Stop and remove VizR container"""
        try:
            # Stop running container
            subprocess.run(
                ["docker", "stop", self.container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace invalid characters
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Remove container
            subprocess.run(
                ["docker", "rm", self.container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace invalid characters
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            print(f"✅ VizR container stopped and removed")
        except Exception as e:
            print(f"⚠️ Failed to stop container: {e}")
            raise

    def pull_image(self):
        """Download latest image from Docker Hub with progress display"""
        try:
            # Use Popen to capture output in real-time
            process = subprocess.Popen(
                ["docker", "pull", self.image_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',  # Force UTF-8 encoding to avoid cp949 errors
                errors='replace',  # Replace invalid characters instead of crashing
                bufsize=1,  # Line buffered
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Read output line by line and update progress
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if line:
                    # Show first 60 characters of docker pull output
                    # (e.g., "Pulling fs layer", "Downloading [==>  ] 123MB/456MB")
                    self.progress_window.update_status(
                        "[4/6] Downloading VizR image...",
                        line[:60]
                    )

            process.wait()
            return process.returncode == 0
        except Exception:
            return False

    def start_container(self):
        """Start VizR container"""
        # Convert Windows path to Docker volume format
        vizr_path_docker = self.convert_windows_path_to_docker(self.vizr_path)

        cmd = [
            "docker", "run",
            "-d",  # Run in background
            "--name", self.container_name,
            "-p", f"{self.port}:{self.port}",
            "-v", f"{vizr_path_docker}:/vizr",
            "-v", f"{vizr_path_docker}/.tmp:/tmp",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-e", "PATH=/opt/venvs/vizr/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "-e", "VIZR_PATH=/vizr",
            "-e", f"HOST_VIZR_PATH={self.vizr_path}",
            "-e", "MODE=production",
            "-e", "DOCKER_API_VERSION=1.44",
            "--privileged",
            self.image_name
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace invalid characters
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def wait_for_server(self, max_wait=120):
        """Wait until server is ready"""
        url = f"http://localhost:{self.port}"

        for i in range(max_wait):
            try:
                response = requests.get(url, timeout=1)
                if response.status_code == 200:
                    return True
            except Exception:
                pass

            time.sleep(1)

            # Update progress every 5 seconds (only if progress_window exists)
            if i % 5 == 0 and hasattr(self, 'progress_window') and self.progress_window:
                try:
                    self.progress_window.update_status(
                        "Waiting for VizR server...",
                        f"Waiting for server to start... ({i}/{max_wait}s)"
                    )
                except Exception:
                    # Ignore errors from progress window updates (e.g., main thread not in main loop)
                    pass

        return False

    def open_browser(self):
        """Open web browser"""
        url = f"http://localhost:{self.port}"
        webbrowser.open(url)

    def run(self):
        """Main execution logic"""
        # Create progress window
        self.progress_window = ProgressWindow()

        try:
            # 1. Check Docker Desktop
            self.progress_window.update_progress(1, 6)
            self.progress_window.update_status(
                "[1/6] Checking Docker Desktop...",
                "Verifying Docker is running."
            )

            if not self.check_docker_running():
                self.progress_window.update_status(
                    "[1/6] Starting Docker Desktop...",
                    "Automatically starting Docker Desktop."
                )

                if not self.start_docker_desktop():
                    self.progress_window.close()
                    messagebox.showerror(
                        "Docker Desktop Required",
                        "Failed to start Docker Desktop.\n\n"
                        "Please install and run Docker Desktop first.\n"
                        "Download: https://www.docker.com/products/docker-desktop"
                    )
                    sys.exit(1)
            else:
                self.progress_window.update_status(
                    "[1/6] Docker Desktop is running",
                    "Docker Desktop is already running."
                )

            # 2. Set VIZR_PATH
            self.progress_window.update_progress(2, 6)
            self.progress_window.update_status(
                "[2/6] Setting up data folder...",
                "Select a folder to store VizR data."
            )
            vizr_path = self.get_vizr_path()

            # 3. Check if container is already running
            self.progress_window.update_progress(3, 6)
            container_already_running = self.check_container_running()

            if container_already_running:
                self.progress_window.update_status(
                    "[3/6] VizR container is already running",
                    "Using existing VizR container."
                )
            else:
                self.progress_window.update_status(
                    "[3/6] Cleaning up existing container...",
                    "Removing previously running VizR container."
                )
                self.stop_existing_container()

            # 4. Download image (skip if container already running)
            self.progress_window.update_progress(4, 6)
            if not container_already_running:
                self.progress_window.update_status(
                    "[4/6] Checking VizR image...",
                    "Verifying latest VizR image from Docker Hub."
                )
                if not self.pull_image():
                    self.progress_window.close()
                    messagebox.showerror(
                        "Image Download Failed",
                        "Failed to download VizR image.\n"
                        "Please check your internet connection and try again."
                    )
                    sys.exit(1)
            else:
                self.progress_window.update_status(
                    "[4/6] Image check skipped",
                    "Container is already running."
                )

            # 5. Start container (skip if already running)
            self.progress_window.update_progress(5, 6)
            if not container_already_running:
                self.progress_window.update_status(
                    "[5/6] Starting VizR container...",
                    "Launching VizR application."
                )
                if not self.start_container():
                    self.progress_window.close()
                    messagebox.showerror(
                        "Container Start Failed",
                        "Failed to start VizR container."
                    )
                    sys.exit(1)
            else:
                self.progress_window.update_status(
                    "[5/6] Container start skipped",
                    "Container is already running."
                )

            # 6. Wait for server
            self.progress_window.update_progress(6, 6)
            self.progress_window.update_status(
                "[6/6] Waiting for VizR server...",
                "Waiting for server to start."
            )
            if not self.wait_for_server():
                self.progress_window.close()
                messagebox.showwarning(
                    "Server Timeout",
                    "Server is taking longer than expected to start.\n"
                    "Please try accessing http://localhost:5001 manually in a moment."
                )
                return

            # 7. Open browser
            self.progress_window.update_status(
                "VizR Started Successfully!",
                "Opening web browser..."
            )
            time.sleep(2)
            self.open_browser()

            # Close progress window
            self.progress_window.close()

            # 8. Start system tray icon
            if TRAY_AVAILABLE:
                tray_icon = VizRTrayIcon(launcher=self)
                tray_icon.run()
            else:
                # Fallback: Show success message if tray not available
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                messagebox.showinfo(
                    "VizR Started",
                    f"VizR has been started successfully!\n\n"
                    f"Web browser: http://localhost:{self.port}\n"
                    f"Data folder: {vizr_path}\n\n"
                    f"Note: System tray icon is not available.\n"
                    f"Close this window to keep VizR running.",
                    parent=root
                )
                root.destroy()

                # Keep the program running
                print("VizR is running. Press Ctrl+C to stop.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nStopping VizR...")
                    self.stop_container()

        except Exception as e:
            if self.progress_window:
                self.progress_window.close()
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")
            sys.exit(1)


class VizRTrayIcon:
    """System tray icon manager for VizR"""

    def __init__(self, launcher):
        """
        Args:
            launcher: VizRLauncher instance for container management
        """
        self.launcher = launcher
        self.icon = None
        self.icon_image = self.create_icon_image()

    def create_icon_image(self):
        """Create tray icon image (simple DNA helix design)"""
        if not PIL_AVAILABLE:
            return None

        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)

        # Simple DNA helix-inspired design
        draw.ellipse([10, 10, 54, 54], fill='#4A90E2', outline='#2E5C8A')
        draw.ellipse([20, 20, 44, 44], fill='white')
        draw.text((22, 24), "VizR", fill='#4A90E2')

        return image

    def show_balloon_notification(self, title, message):
        """
        Show balloon notification using Windows native API

        Args:
            title: Notification title
            message: Notification message
        """
        # Log to console
        print(f"ℹ️ {title}: {message}")

        # Try pystray notification if available
        if self.icon:
            try:
                self.icon.notify(title=title, message=message)
            except Exception as e:
                print(f"⚠️ Tray notification failed: {e}")

    def on_open_clicked(self, icon, item):
        """Open VizR web interface - Thread-safe version"""
        def open_browser():
            """Open browser in separate thread"""
            self.show_balloon_notification(
                title="VizR",
                message="Opening VizR web interface..."
            )
            webbrowser.open(f'http://localhost:{self.launcher.port}')

        # Run in separate thread to avoid blocking pystray event loop
        threading.Thread(target=open_browser, daemon=True).start()

    def show_native_messagebox(self, title, message, style=0):
        """
        Show Windows native MessageBox (works in remote desktop)

        Args:
            title: Dialog title
            message: Dialog message
            style: MessageBox style (0=OK, 1=OK/Cancel, 4=Yes/No, etc.)

        Returns:
            Button clicked (1=OK/Yes, 2=Cancel/No, etc.)
        """
        MB_OK = 0
        MB_ICONINFORMATION = 64
        MB_ICONERROR = 16
        MB_YESNO = 4
        MB_ICONQUESTION = 32
        MB_TOPMOST = 0x40000

        try:
            return ctypes.windll.user32.MessageBoxW(0, message, title, style | MB_TOPMOST)
        except Exception as e:
            print(f"⚠️ MessageBox error: {e}")
            return 0

    def browse_folder_native(self, title="Select Folder"):
        """
        Show Windows native folder browser dialog using PowerShell
        (Works in remote desktop environments)

        Args:
            title: Dialog title

        Returns:
            Selected folder path or None if cancelled
        """
        try:
            # Use PowerShell to show folder browser dialog
            script = f'''
Add-Type -AssemblyName System.Windows.Forms
$browser = New-Object System.Windows.Forms.FolderBrowserDialog
$browser.Description = "{title}"
$browser.ShowNewFolderButton = $true
$browser.RootFolder = "MyComputer"
if ($browser.ShowDialog() -eq "OK") {{
    Write-Output $browser.SelectedPath
}}
'''
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                path = result.stdout.strip()
                if path:
                    return path
            return None
        except Exception as e:
            print(f"⚠️ Folder browser error: {e}")
            return None

    def on_settings_clicked(self, icon, item):
        """Settings menu - Change VIZR_PATH - Using native Windows dialogs"""
        def show_settings():
            """Show settings dialog in separate thread"""
            current_path = self.read_config()

            if not current_path:
                self.show_native_messagebox(
                    "Configuration Error",
                    "Cannot read current VizR data path.\n\n"
                    "Please reinstall VizR using VizR_Setup.exe.",
                    style=16  # MB_ICONERROR
                )
                return

            # Show folder selection dialog using native Windows API
            new_path = self.browse_folder_native("Select VizR Data Folder")

            if not new_path:
                return  # User cancelled

            if new_path == current_path:
                self.show_native_messagebox(
                    "No Changes",
                    "You selected the same folder. No changes made.",
                    style=64  # MB_ICONINFORMATION
                )
                return

            # Update config file
            try:
                self.update_config(new_path)
            except Exception as e:
                self.show_native_messagebox(
                    "Configuration Update Failed",
                    f"Failed to update configuration file:\n\n{str(e)}",
                    style=16  # MB_ICONERROR
                )
                return

            # Ask for container restart
            result = self.show_native_messagebox(
                "VizR Restart Required",
                f"VizR data path has been changed:\n\n"
                f"From: {current_path}\n"
                f"To: {new_path}\n\n"
                f"VizR container must be restarted to apply the new path.\n\n"
                f"Restart VizR now?",
                style=4 | 32  # MB_YESNO | MB_ICONQUESTION
            )

            if result == 6:  # IDYES
                try:
                    # Show restart notification
                    self.show_balloon_notification(
                        title="VizR Restarting",
                        message="Stopping VizR container..."
                    )

                    # Stop container
                    self.launcher.stop_container()

                    # Update launcher's vizr_path
                    self.launcher.vizr_path = new_path

                    # Start container with new path
                    self.show_balloon_notification(
                        title="VizR Restarting",
                        message="Starting VizR with new data path..."
                    )

                    self.launcher.start_container()

                    # Wait for server
                    if self.launcher.wait_for_server(max_wait=60):
                        self.show_balloon_notification(
                            title="VizR Restarted",
                            message=f"VizR is now using:\n{new_path}"
                        )

                        self.show_native_messagebox(
                            "VizR Restarted",
                            f"VizR has been successfully restarted.\n\n"
                            f"New data path:\n{new_path}",
                            style=64  # MB_ICONINFORMATION
                        )
                    else:
                        self.show_native_messagebox(
                            "Restart Failed",
                            "VizR container started but server is not responding.\n\n"
                            "Please check the logs or restart VizR manually.",
                            style=16  # MB_ICONERROR
                        )
                except Exception as e:
                    self.show_native_messagebox(
                        "Restart Failed",
                        f"Failed to restart VizR container:\n\n{str(e)}",
                        style=16  # MB_ICONERROR
                    )
            else:
                self.show_native_messagebox(
                    "Restart Later",
                    "VizR data path has been updated in the configuration.\n\n"
                    "Changes will take effect when you restart VizR next time.",
                    style=64  # MB_ICONINFORMATION
                )

        # Run in separate thread to avoid blocking pystray event loop
        threading.Thread(target=show_settings, daemon=False).start()

    def on_quit_clicked(self, icon, item):
        """Exit VizR - Using native Windows dialogs"""
        def ask_and_quit():
            """Ask user and quit"""
            result = self.show_native_messagebox(
                "Exit VizR",
                "Do you want to stop VizR container and exit?\n\n"
                "This will stop all running RNA-Seq analysis jobs.",
                style=4 | 32  # MB_YESNO | MB_ICONQUESTION
            )

            if result == 6:  # IDYES
                try:
                    self.launcher.stop_container()
                    print("✅ VizR container stopped")
                except Exception as e:
                    print(f"⚠️ Failed to stop container: {e}")

                # Stop tray icon
                icon.stop()

        # Run in separate thread to avoid blocking pystray event loop
        threading.Thread(target=ask_and_quit, daemon=False).start()

    def create_menu(self):
        """Create tray icon right-click menu"""
        if not TRAY_AVAILABLE:
            return None

        return pystray.Menu(
            pystray.MenuItem(
                "Open VizR",
                self.on_open_clicked,
                default=True
            ),
            pystray.MenuItem(
                "Change Data Path",
                self.on_settings_clicked
            ),
            pystray.MenuItem(
                "Exit",
                self.on_quit_clicked
            )
        )

    def run(self):
        """Run tray icon (main loop)"""
        if not TRAY_AVAILABLE:
            print("⚠️ System tray not available. Running without tray icon.")
            return

        self.icon = pystray.Icon(
            name="VizR",
            icon=self.icon_image,
            title="VizR - RNA-Seq Analysis Platform",
            menu=self.create_menu()
        )

        # Schedule balloon notification to show after icon is registered
        def show_initial_notification():
            self.show_balloon_notification(
                title="VizR is running in the background",
                message="Click the system tray icon to open VizR."
            )

        timer = threading.Timer(1.0, show_initial_notification)
        timer.daemon = True
        timer.start()

        # Run tray icon (blocking)
        self.icon.run()

    def read_config(self):
        """Read VIZR_PATH from config file"""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(__file__)

        config_file = os.path.join(exe_dir, '.vizr_config.json')

        if not os.path.exists(config_file):
            return ''

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('vizr_path', '')
        except Exception as e:
            print(f"⚠️ Failed to read config file: {e}")
            return ''

    def update_config(self, new_path):
        """Update VIZR_PATH in config file"""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(__file__)

        config_file = os.path.join(exe_dir, '.vizr_config.json')

        # Read existing config
        config = {}
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                pass

        # Update VIZR_PATH
        config['vizr_path'] = new_path
        config['updated_at'] = datetime.now().isoformat()

        # Save config file
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"✅ Config file updated: {new_path}")
        except Exception as e:
            print(f"❌ Failed to update config file: {e}")
            raise


if __name__ == "__main__":
    try:
        launcher = VizRLauncher()
        launcher.run()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")
        sys.exit(1)
