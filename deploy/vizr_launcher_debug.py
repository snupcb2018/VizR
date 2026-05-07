#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VizR Launcher - Debug Version with Console Logging
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

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Enable debug logging
DEBUG = True

def debug_log(message):
    """Print debug message if DEBUG is enabled"""
    if DEBUG:
        print(f"[DEBUG] {message}")

class ProgressWindow:
    """Modern splash screen without title bar"""
    def __init__(self):
        debug_log("Creating ProgressWindow")
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
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(__file__)

            logo_path = os.path.join(base_path, "vizr_logo.png")
            debug_log(f"Looking for logo at: {logo_path}")
            if os.path.exists(logo_path):
                try:
                    img = Image.open(logo_path)
                    img = img.resize((150, 150), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)

                    logo_label = tk.Label(
                        logo_frame,
                        image=photo,
                        bg="white"
                    )
                    logo_label.image = photo
                    logo_label.pack(expand=True)
                    logo_loaded = True
                    debug_log("Logo loaded successfully")
                except Exception as e:
                    debug_log(f"Logo load failed: {e}")

        # If no image loaded, show text placeholder
        if not logo_loaded:
            debug_log("Using text placeholder")
            logo_label = tk.Label(
                logo_frame,
                text="VizR",
                font=("Segoe UI", 48, "bold"),
                fg="#0066CC",
                bg="white"
            )
            logo_label.pack(expand=True)

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
        debug_log("ProgressWindow created")

    def update_status(self, status, detail=""):
        """Update status message"""
        if detail:
            message = f"{status}\n{detail}"
        else:
            message = status
        debug_log(f"Status: {status} | Detail: {detail}")
        self.status_label.config(text=message)
        self.root.update()

    def update_progress(self, current, total):
        """Update progress (not displayed in splash screen)"""
        pass

    def close(self):
        """Close window"""
        debug_log("Closing ProgressWindow")
        self.root.destroy()


class VizRLauncher:
    def __init__(self):
        debug_log("Initializing VizRLauncher")
        self.container_name = "vizr"
        self.image_name = "hjung200x/vizr:latest"
        self.port = 5001
        self.vizr_path = None
        self.progress_window = None

    def check_docker_running(self):
        """Check if Docker Desktop is running"""
        debug_log("Checking if Docker is running...")
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_running = result.returncode == 0
            debug_log(f"Docker running: {is_running}")
            return is_running
        except Exception as e:
            debug_log(f"Docker check failed: {e}")
            return False

    def check_container_running(self):
        """Check if VizR container is already running"""
        debug_log("Checking if VizR container is running...")
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={self.container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_running = self.container_name in result.stdout
            debug_log(f"Container running: {is_running}")
            debug_log(f"Docker ps output: {result.stdout.strip()}")
            return is_running
        except Exception as e:
            debug_log(f"Container check failed: {e}")
            return False

    def start_docker_desktop(self):
        """Auto-start Docker Desktop (Tray Icon mode)"""
        debug_log("Starting Docker Desktop...")
        docker_desktop_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"

        if not os.path.exists(docker_desktop_path):
            debug_log(f"Docker Desktop not found at: {docker_desktop_path}")
            return False

        subprocess.Popen([docker_desktop_path, "--openui=false"])
        debug_log("Docker Desktop process started")

        # Wait for Docker daemon to be ready (max 60 seconds)
        for i in range(60):
            if self.check_docker_running():
                debug_log(f"Docker ready after {i} seconds")
                return True

            if i % 5 == 0:
                self.progress_window.update_status(
                    "Starting Docker Desktop...",
                    f"Waiting... ({i}/60s)"
                )

            time.sleep(1)

        debug_log("Docker Desktop start timeout")
        return False

    def get_vizr_path(self):
        """Get or set VIZR_PATH"""
        debug_log("Getting VIZR_PATH...")
        vizr_path = os.environ.get("VIZR_PATH")

        if not vizr_path:
            default_path = os.path.join(os.path.expanduser("~"), "VizR_Data")
            debug_log(f"VIZR_PATH not set, suggesting: {default_path}")

            root = tk.Tk()
            root.withdraw()

            result = messagebox.askyesno(
                "VizR Data Folder Setup",
                f"Please select a folder to store VizR data.\n\n"
                f"Default path: {default_path}\n\n"
                f"Use default path?"
            )

            if result:
                vizr_path = default_path
            else:
                vizr_path = filedialog.askdirectory(
                    title="Select VizR Data Folder",
                    initialdir=os.path.expanduser("~")
                )
                if not vizr_path:
                    debug_log("No folder selected")
                    messagebox.showerror("Error", "No folder selected.")
                    sys.exit(1)

            root.destroy()

        Path(vizr_path).mkdir(parents=True, exist_ok=True)
        self.vizr_path = vizr_path
        debug_log(f"VIZR_PATH set to: {vizr_path}")

        return vizr_path

    def stop_existing_container(self):
        """Remove existing stopped VizR container"""
        debug_log("Removing existing stopped container...")
        try:
            result = subprocess.run(
                ["docker", "rm", self.container_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            debug_log(f"Container removal result: {result.returncode}")
            debug_log(f"stdout: {result.stdout}")
            debug_log(f"stderr: {result.stderr}")
        except Exception as e:
            debug_log(f"Container removal failed: {e}")

    def pull_image(self):
        """Download latest image from Docker Hub"""
        debug_log(f"Pulling image: {self.image_name}")
        try:
            result = subprocess.run(
                ["docker", "pull", self.image_name],
                check=True,
                capture_output=True,
                text=True
            )
            debug_log("Image pull successful")
            return True
        except Exception as e:
            debug_log(f"Image pull failed: {e}")
            return False

    def start_container(self):
        """Start VizR container"""
        debug_log("Starting VizR container...")

        # Convert Windows path to Docker volume format
        vizr_path_docker = self.vizr_path.replace("\\", "/")
        if vizr_path_docker[1] == ":":
            vizr_path_docker = f"/{vizr_path_docker[0].lower()}{vizr_path_docker[2:]}"

        debug_log(f"Docker path: {vizr_path_docker}")

        cmd = [
            "docker", "run",
            "-d",
            "--name", self.container_name,
            "-p", f"{self.port}:{self.port}",
            "-v", f"{vizr_path_docker}:/vizr",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-e", f"VIZR_PATH=/vizr",
            "-e", "MODE=production",
            self.image_name
        ]

        debug_log(f"Docker command: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            debug_log("Container started successfully")
            debug_log(f"Container ID: {result.stdout.strip()}")
            return True
        except subprocess.CalledProcessError as e:
            debug_log(f"Container start failed: {e}")
            debug_log(f"stdout: {e.stdout}")
            debug_log(f"stderr: {e.stderr}")
            return False

    def wait_for_server(self, max_wait=120):
        """Wait until server is ready"""
        debug_log(f"Waiting for server (max {max_wait}s)...")
        url = f"http://localhost:{self.port}"

        for i in range(max_wait):
            try:
                response = requests.get(url, timeout=1)
                if response.status_code == 200:
                    debug_log(f"Server ready after {i} seconds")
                    return True
            except Exception:
                pass

            time.sleep(1)

            if i % 5 == 0:
                self.progress_window.update_status(
                    "Waiting for VizR server...",
                    f"Waiting for server to start... ({i}/{max_wait}s)"
                )

        debug_log("Server wait timeout")
        return False

    def open_browser(self):
        """Open web browser"""
        url = f"http://localhost:{self.port}"
        debug_log(f"Opening browser: {url}")
        webbrowser.open(url)

    def run(self):
        """Main execution logic"""
        debug_log("=== VizR Launcher Started ===")

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
            time.sleep(1)
            self.open_browser()

            # Close progress window
            self.progress_window.close()

            # Success message - bring to front
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            messagebox.showinfo(
                "VizR Started",
                f"VizR has been started successfully!\n\n"
                f"Web browser: http://localhost:{self.port}\n"
                f"Data folder: {vizr_path}",
                parent=root
            )
            root.destroy()
            debug_log("=== VizR Launcher Completed Successfully ===")

        except Exception as e:
            debug_log(f"Fatal error: {e}")
            import traceback
            traceback.print_exc()
            if self.progress_window:
                self.progress_window.close()
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")
            sys.exit(1)


if __name__ == "__main__":
    try:
        launcher = VizRLauncher()
        launcher.run()
    except KeyboardInterrupt:
        debug_log("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        debug_log(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")
        sys.exit(1)
