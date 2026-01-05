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
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import yt_dlp


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


def download_audio(video_url, output_widget):
    print(f"Starting audio extraction for URL: {video_url}")

    cwd = os.getcwd()
    print(f"Download location (current working directory): {cwd}")

    def progress_hook(d):
        if d['status'] == 'downloading':
            msg = f"Downloading: {d.get('_percent_str', 'N/A')} at {d.get('_speed_str', 'N/A')} ETA: {d.get('_eta_str', 'N/A')}\n"
            output_widget.insert(tk.END, msg)
            output_widget.see(tk.END)
            output_widget.update()
        elif d['status'] == 'finished':
            msg = f"Download finished, now processing...\n"
            output_widget.insert(tk.END, msg)
            output_widget.see(tk.END)
            output_widget.update()

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title).80B [%(id)s].%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '0',
        }],
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en.*'],
        'convertsubtitles': 'srt',
        'sleep_interval': 2,
        'max_sleep_interval': 5,
        'retries': 20,
        'fragment_retries': 20,
        'concurrent_fragment_downloads': 1,
        'progress_hooks': [progress_hook],
        'quiet': False,
        'no_warnings': False,
    }

    try:
        output_widget.insert(tk.END, f"Starting MP3 extraction for: {video_url}\n")
        output_widget.insert(tk.END, f"Download directory: {cwd}\n")
        output_widget.insert(tk.END, "-" * 80 + "\n")
        output_widget.see(tk.END)
        output_widget.update()

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Starting yt-dlp MP3 extraction...")
            info = ydl.extract_info(video_url, download=True)
            print(f"MP3 extraction completed for: {info.get('title', 'Unknown')}")

        print("MP3 extraction completed successfully")
        output_widget.insert(tk.END, "\n" + "=" * 80 + "\n")
        output_widget.insert(tk.END, "MP3 extraction completed successfully!\n")
        output_widget.insert(tk.END, "=" * 80 + "\n")
        output_widget.see(tk.END)
        messagebox.showinfo("Success", "MP3 extraction completed successfully!")

    except Exception as e:
        error_msg = f"Error during MP3 extraction: {str(e)}"
        print(error_msg)
        output_widget.insert(tk.END, f"\n{error_msg}\n")
        output_widget.see(tk.END)
        messagebox.showerror("Download Error", error_msg)


def start_download_thread(url_entry, output_widget, download_button):
    video_url = url_entry.get().strip()

    if not video_url:
        print("No URL provided")
        messagebox.showwarning("No URL", "Please enter a video URL")
        return

    print(f"URL entered: {video_url}")

    download_button.config(state=tk.DISABLED, text="Extracting Audio...")

    thread = threading.Thread(
        target=lambda: download_and_enable_button(video_url, output_widget, download_button),
        daemon=True
    )
    thread.start()


def download_and_enable_button(video_url, output_widget, download_button):
    try:
        download_audio(video_url, output_widget)
    finally:
        download_button.config(state=tk.NORMAL, text="Extract MP3")


def create_gui():
    print("Creating GUI window...")

    root = tk.Tk()
    root.title("YT-DLP MP3 Extractor with English Subtitles (Administrator Mode)")
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
        text="YT-DLP: Python Library (Installed)",
        font=("Arial", 9),
        fg="white",
        bg="#1C1C1C",
        anchor="w"
    ).pack(fill=tk.X)

    input_frame = tk.Frame(root, padx=10, pady=5, bg="#1C1C1C")
    input_frame.pack(fill=tk.X)

    tk.Label(
        input_frame,
        text="Video URL:",
        font=("Arial", 10, "bold"),
        fg="white",
        bg="#1C1C1C"
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
        text="Extract MP3",
        font=("Arial", 10, "bold"),
        bg="#FF9800",
        fg="white",
        padx=20,
        pady=5,
        command=lambda: start_download_thread(url_entry, output_text, download_button)
    )
    download_button.pack(side=tk.LEFT)

    output_frame = tk.Frame(root, padx=10, pady=5, bg="#1C1C1C")
    output_frame.pack(fill=tk.BOTH, expand=True)

    tk.Label(
        output_frame,
        text="Extraction Output:",
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

    button_frame = tk.Frame(root, padx=10, pady=10, bg="#1C1C1C")
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
    output_text.insert(tk.END, "YT-DLP MP3 Extractor Ready\n")
    output_text.insert(tk.END, "=" * 80 + "\n")
    output_text.insert(tk.END, f"Working Directory: {cwd}\n")
    output_text.insert(tk.END, f"YT-DLP: Python Library v{yt_dlp.version.__version__}\n")
    output_text.insert(tk.END, "=" * 80 + "\n\n")
    output_text.insert(tk.END, "Audio Format: MP3 (Best Quality - Audio Quality 0)\n")
    output_text.insert(tk.END, "Subtitles: English variants (auto-generated + manual), converted to SRT\n")
    output_text.insert(tk.END, "=" * 80 + "\n\n")
    output_text.insert(tk.END, "Enter a video URL and click 'Extract MP3' to begin.\n\n")

    print("Starting GUI main loop...")
    root.mainloop()


def main():
    print("=" * 80)
    print("YT-DLP MP3 Extractor with English Subtitles (Administrator Mode)")
    print("=" * 80)

    if not is_admin():
        elevate_privileges()

    print("Running with administrator privileges")

    cwd = os.getcwd()
    print(f"Current working directory: {cwd}")

    try:
        print(f"YT-DLP library version: {yt_dlp.version.__version__}")
    except Exception as e:
        print(f"Error getting yt-dlp version: {e}")

    create_gui()

    print("Application closed")


if __name__ == "__main__":
    main()
