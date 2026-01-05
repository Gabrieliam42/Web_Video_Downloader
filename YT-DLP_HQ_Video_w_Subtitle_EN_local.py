import sys
import os

if getattr(sys, 'frozen', False):
    python_root = r'C:\Program Files\Python312'
    if not os.path.exists(python_root):
        python_root = sys.base_prefix
    print(f"Running as PyInstaller bundle. Using system Python: {python_root}")
else:
    python_root = sys.base_prefix
    print(f"Running as Python script. Using Python: {python_root}")

tcl_library_path = os.path.join(python_root, 'tcl', 'tcl8.6')
tk_library_path = os.path.join(python_root, 'tcl', 'tk8.6')

if not os.path.exists(tcl_library_path):
    print(f"WARNING: TCL library not found at {tcl_library_path}")
if not os.path.exists(tk_library_path):
    print(f"WARNING: TK library not found at {tk_library_path}")

os.environ['TCL_LIBRARY'] = tcl_library_path
os.environ['TK_LIBRARY'] = tk_library_path
print(f"TCL_LIBRARY: {tcl_library_path}")
print(f"TK_LIBRARY: {tk_library_path}")

import ctypes
import subprocess
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading


def is_admin():
    print("Checking for administrator privileges...")
    try:
        admin_status = ctypes.windll.shell32.IsUserAnAdmin()
        print(f"Administrator status: {admin_status}")
        return admin_status
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False


def elevate_privileges():
    print("Not running as administrator. Attempting to elevate privileges...")
    try:
        script_path = os.path.abspath(sys.argv[0])
        print(f"Script path: {script_path}")

        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        print(f"Parameters: {params}")

        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script_path}" {params}',
            None,
            1
        )

        print(f"ShellExecuteW return value: {ret}")

        if ret > 32:
            print("Successfully spawned elevated process. Exiting non-elevated instance.")
            sys.exit(0)
        else:
            print(f"Failed to elevate. Return code: {ret}")
            messagebox.showerror("Elevation Failed", f"Could not elevate privileges. Error code: {ret}")
            sys.exit(1)

    except Exception as e:
        print(f"Error during elevation: {e}")
        messagebox.showerror("Elevation Error", f"Failed to elevate: {str(e)}")
        sys.exit(1)


def find_ytdlp_exe(cwd):
    print(f"Searching for yt-dlp.exe in current working directory: {cwd}")

    ytdlp_locations = []

    # If running as PyInstaller bundle, check the temporary extraction directory first
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        print(f"Running as frozen executable. Bundle directory: {bundle_dir}")
        ytdlp_locations.extend([
            os.path.join(bundle_dir, "yt-dlp.exe"),
            os.path.join(bundle_dir, "_internal", "yt-dlp.exe")
        ])

    # Always check current working directory
    ytdlp_locations.extend([
        os.path.join(cwd, "yt-dlp.exe"),
        os.path.join(cwd, "_internal", "yt-dlp.exe")
    ])

    for location in ytdlp_locations:
        print(f"Checking location: {location}")
        if os.path.exists(location):
            print(f"Found yt-dlp.exe at: {location}")
            return location

    print("Searching through all subdirectories using os.walk()...")
    for root, dirs, files in os.walk(cwd):
        for file in files:
            if file.lower() == "yt-dlp.exe":
                full_path = os.path.join(root, file)
                print(f"Found yt-dlp.exe at: {full_path}")
                return full_path

    print("ERROR: yt-dlp.exe not found in current working directory or subdirectories")
    return None


def download_video(ytdlp_path, video_url, output_widget):
    print(f"Starting download process for URL: {video_url}")
    print(f"Using yt-dlp.exe from: {ytdlp_path}")

    cwd = os.getcwd()
    print(f"Download location (current working directory): {cwd}")

    command = [
        ytdlp_path,
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "--merge-output-format", "mp4",
        "--windows-filenames",
        "--trim-filenames", "120",
        "-o", "%(title).80B [%(id)s].%(ext)s",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en",
        "--convert-subs", "srt",
        "--hls-prefer-ffmpeg",
        "--force-ipv4",
        "--sleep-requests", "2",
        "--min-sleep-interval", "2",
        "--max-sleep-interval", "5",
        "--retries", "20",
        "--fragment-retries", "20",
        "-N", "1",
        video_url
    ]

    print("Command to execute:")
    print(' '.join(command))

    try:
        output_widget.insert(tk.END, f"Starting download for: {video_url}\n")
        output_widget.insert(tk.END, f"Download directory: {cwd}\n")
        output_widget.insert(tk.END, "-" * 80 + "\n")
        output_widget.see(tk.END)
        output_widget.update()

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        print("Process started. Reading output...")

        for line in iter(process.stdout.readline, ''):
            if line:
                print(line.rstrip())
                output_widget.insert(tk.END, line)
                output_widget.see(tk.END)
                output_widget.update()

        process.wait()

        if process.returncode == 0:
            print("Download completed successfully")
            output_widget.insert(tk.END, "\n" + "=" * 80 + "\n")
            output_widget.insert(tk.END, "Download completed successfully!\n")
            output_widget.insert(tk.END, "=" * 80 + "\n")
            output_widget.see(tk.END)
            messagebox.showinfo("Success", "Download completed successfully!")
        else:
            print(f"Download failed with return code: {process.returncode}")
            output_widget.insert(tk.END, f"\nDownload failed with error code: {process.returncode}\n")
            output_widget.see(tk.END)
            messagebox.showerror("Error", f"Download failed with error code: {process.returncode}")

    except Exception as e:
        error_msg = f"Error during download: {str(e)}"
        print(error_msg)
        output_widget.insert(tk.END, f"\n{error_msg}\n")
        output_widget.see(tk.END)
        messagebox.showerror("Download Error", error_msg)


def start_download_thread(ytdlp_path, url_entry, output_widget, download_button):
    video_url = url_entry.get().strip()

    if not video_url:
        print("No URL provided")
        messagebox.showwarning("No URL", "Please enter a video URL")
        return

    print(f"URL entered: {video_url}")

    download_button.config(state=tk.DISABLED, text="Downloading...")

    thread = threading.Thread(
        target=lambda: download_and_enable_button(ytdlp_path, video_url, output_widget, download_button),
        daemon=True
    )
    thread.start()


def download_and_enable_button(ytdlp_path, video_url, output_widget, download_button):
    try:
        download_video(ytdlp_path, video_url, output_widget)
    finally:
        download_button.config(state=tk.NORMAL, text="Download Video")


def create_gui(ytdlp_path):
    print("Creating GUI window...")

    root = tk.Tk()
    root.title("YT-DLP Video Downloader (Administrator Mode)")
    root.geometry("900x600")
    root.resizable(True, True)
    root.configure(bg="#1C1C1C")

    cwd = os.getcwd()

    info_frame = tk.Frame(root, padx=10, pady=10, bg="#1C1C1C")
    info_frame.pack(fill=tk.X)

    tk.Label(
        info_frame,
        text=f"Download Directory: {cwd}",
        font=("Arial", 9),
        fg="white",
        bg="#1C1C1C",
        anchor="w"
    ).pack(fill=tk.X)

    tk.Label(
        info_frame,
        text=f"YT-DLP Location: {ytdlp_path}",
        font=("Arial", 9),
        fg="white",
        bg="#1C1C1C",
        anchor="w"
    ).pack(fill=tk.X)

    input_frame = tk.Frame(root, padx=10, pady=5, bg="#36454F")
    input_frame.pack(fill=tk.X)

    tk.Label(
        input_frame,
        text="Video URL:",
        font=("Arial", 10, "bold"),
        fg="white",
        bg="#36454F"
    ).pack(side=tk.LEFT, padx=(0, 10))

    url_var = tk.StringVar(master=root)
    url_entry = tk.Entry(
        input_frame,
        textvariable=url_var,
        font=("Arial", 10),
        width=60,
        bg="#2B2B2B",
        fg="white",
        insertbackground="white"
    )
    url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

    download_button = tk.Button(
        input_frame,
        text="Download Video",
        font=("Arial", 10, "bold"),
        bg="#4CAF50",
        fg="white",
        padx=20,
        pady=5,
        command=lambda: start_download_thread(ytdlp_path, url_entry, output_text, download_button)
    )
    download_button.pack(side=tk.LEFT)

    output_frame = tk.Frame(root, padx=10, pady=5, bg="#36454F")
    output_frame.pack(fill=tk.BOTH, expand=True)

    tk.Label(
        output_frame,
        text="Download Output:",
        font=("Arial", 10, "bold"),
        fg="white",
        bg="#1C1C1C",
        anchor="w"
    ).pack(fill=tk.X)

    output_text = scrolledtext.ScrolledText(
        output_frame,
        font=("Consolas", 9),
        bg="#1C1C1C",
        fg="white",
        insertbackground="white",
        wrap=tk.WORD
    )
    output_text.pack(fill=tk.BOTH, expand=True)

    button_frame = tk.Frame(root, padx=10, pady=10, bg="#36454F")
    button_frame.pack(fill=tk.X)

    clear_button = tk.Button(
        button_frame,
        text="Clear Output",
        font=("Arial", 9),
        bg="#2B2B2B",
        fg="white",
        command=lambda: output_text.delete(1.0, tk.END)
    )
    clear_button.pack(side=tk.LEFT, padx=(0, 10))

    exit_button = tk.Button(
        button_frame,
        text="Exit",
        font=("Arial", 9),
        bg="#2B2B2B",
        fg="white",
        command=root.quit
    )
    exit_button.pack(side=tk.LEFT)

    print("GUI created successfully")
    output_text.insert(tk.END, "YT-DLP Video Downloader Ready\n")
    output_text.insert(tk.END, "=" * 80 + "\n")
    output_text.insert(tk.END, f"Working Directory: {cwd}\n")
    output_text.insert(tk.END, f"YT-DLP Path: {ytdlp_path}\n")
    output_text.insert(tk.END, "=" * 80 + "\n\n")
    output_text.insert(tk.END, "Enter a video URL and click 'Download Video' to begin.\n\n")

    print("Starting GUI main loop...")
    root.mainloop()


def main():
    print("=" * 80)
    print("YT-DLP Video Downloader with Administrator Privileges")
    print("=" * 80)

    if not is_admin():
        elevate_privileges()

    print("Running with administrator privileges")

    cwd = os.getcwd()
    print(f"Current working directory: {cwd}")

    print("\nScanning directory contents:")
    for root, dirs, files in os.walk(cwd):
        level = root.replace(cwd, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        sub_indent = ' ' * 2 * (level + 1)
        for file in files[:10]:
            print(f"{sub_indent}{file}")
        if len(files) > 10:
            print(f"{sub_indent}... and {len(files) - 10} more files")
        if level >= 2:
            break

    ytdlp_path = find_ytdlp_exe(cwd)

    if ytdlp_path is None:
        error_msg = "yt-dlp.exe not found in the current working directory or _internal subdirectory"
        print(error_msg)
        messagebox.showerror("YT-DLP Not Found", error_msg)
        sys.exit(1)

    create_gui(ytdlp_path)

    print("Application closed")


if __name__ == "__main__":
    main()
