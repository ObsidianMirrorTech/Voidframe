import os
import subprocess
import tempfile
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox


def find_ffmpeg():
    """Try to locate ffmpeg in PATH; return path or empty string."""
    return shutil.which("ffmpeg") or ""


def is_valid_mp4(path, ffmpeg_exec):
    """
    Probes the file for a valid MP4 structure (moov atom). Returns True if valid.
    """
    try:
        subprocess.run([
            ffmpeg_exec,
            "-v", "error",
            "-i", path,
            "-t", "1",
            "-f", "null",
            "-"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def remux_clip(orig_path, ffmpeg_exec):
    """
    Attempts to remux a corrupted clip to rebuild its moov atom.
    Returns the new temp file path if successful, else None.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        subprocess.run([
            ffmpeg_exec,
            "-y",
            "-i", orig_path,
            "-c", "copy",
            tmp_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if is_valid_mp4(tmp_path, ffmpeg_exec):
            return tmp_path
        else:
            os.remove(tmp_path)
            return None
    except subprocess.CalledProcessError:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None


def combine_clips(input_dir, output_path, ffmpeg_exec):
    """
    Combines clips into one video, re-encoding audio to AAC, remuxing corrupt clips if needed.
    """
    clips = []
    remuxed_files = []

    for hour in sorted(os.listdir(input_dir), key=lambda x: int(x)):
        hour_dir = os.path.join(input_dir, hour)
        if not os.path.isdir(hour_dir):
            continue
        for minute_file in sorted(os.listdir(hour_dir), key=lambda x: int(os.path.splitext(x)[0])):
            orig = os.path.join(hour_dir, minute_file)
            if not os.path.isfile(orig):
                continue

            if is_valid_mp4(orig, ffmpeg_exec):
                clips.append(orig)
            else:
                print(f"Attempting to remux corrupted clip: {orig}")
                fixed = remux_clip(orig, ffmpeg_exec)
                if fixed:
                    clips.append(fixed)
                    remuxed_files.append(fixed)
                else:
                    print(f"Skipping clip after failed remux: {orig}")

    if not clips:
        raise ValueError(f"No valid clips found in {input_dir}")

    # Write concat list
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as list_file:
        for clip in clips:
            entry = clip.replace('\\', '/')
            list_file.write(f"file '{entry}'\n")
        list_path = list_file.name

    cmd = [
        ffmpeg_exec,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path
    ]
    subprocess.run(cmd, check=True)
    os.remove(list_path)

    # Clean up remuxed temp files
    for temp_file in remuxed_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)


def select_folder():
    folder = filedialog.askdirectory(title="Select Parent Folder")
    if folder:
        folder_var.set(folder)


def select_ffmpeg():
    exe = filedialog.askopenfilename(
        title="Select ffmpeg executable",
        filetypes=[("Executable", "*.exe"), ("All files", "*")]
    )
    if exe:
        ffmpeg_var.set(exe)


def compile_video():
    input_dir = folder_var.get()
    if not input_dir:
        messagebox.showerror("Error", "Please select a folder first.")
        return

    output_file = filedialog.asksaveasfilename(
        title="Save Combined Video As",
        defaultextension=".mp4",
        filetypes=[("MP4 files", "*.mp4")]
    )
    if not output_file:
        return

    ffmpeg_exec = ffmpeg_var.get() or find_ffmpeg()
    if not ffmpeg_exec or not os.path.isfile(ffmpeg_exec):
        messagebox.showerror("Error", "ffmpeg executable not found. Please set its path.")
        return

    try:
        combine_clips(input_dir, output_file, ffmpeg_exec)
        messagebox.showinfo("Success", f"Video saved to {output_file}")
    except subprocess.CalledProcessError:
        messagebox.showerror("Error", "ffmpeg encountered an error. Check the console for details.")
    except Exception as e:
        messagebox.showerror("Error", str(e))


def main():
    global folder_var, ffmpeg_var
    root = tk.Tk()
    root.title("Roku Daily Video Combiner")

    folder_var = tk.StringVar()
    ffmpeg_var = tk.StringVar(value=find_ffmpeg())

    frame = tk.Frame(root, padx=10, pady=10)
    frame.pack()

    tk.Label(frame, text="Selected Folder:").grid(row=0, column=0, sticky="w")
    tk.Entry(frame, textvariable=folder_var, width=40).grid(row=0, column=1, padx=5)
    tk.Button(frame, text="Select Folder", command=select_folder).grid(row=0, column=2)

    tk.Label(frame, text="ffmpeg Path:").grid(row=1, column=0, sticky="w")
    tk.Entry(frame, textvariable=ffmpeg_var, width=40).grid(row=1, column=1, padx=5)
    tk.Button(frame, text="Browse...", command=select_ffmpeg).grid(row=1, column=2)

    tk.Button(frame, text="Compile Video", command=compile_video).grid(row=2, column=0, columnspan=3, pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()
