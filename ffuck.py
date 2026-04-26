#!/usr/bin/env python3
import os
import signal
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_TITLE = "ffuck.mp0"
DEFAULT_OUTPUT_DIR = str(Path.cwd() / "output")
DEFAULT_FILENAME = "video"
DEFAULT_SIZE = "1280x720"
DEFAULT_THEME = "light"
DEFAULT_DISPLAY = ":0.0"

proc = None
paused = False
chunk_visible = False

root = tk.Tk()
root.title(APP_TITLE)
root.geometry("860x560")
root.resizable(False, False)

style = ttk.Style()

def apply_theme(name):
    themes = {
        "light": {"bg": "#f2f2f2", "fg": "#111111", "fieldbg": "#ffffff", "accent": "#0078d7"},
        "dark": {"bg": "#1d1f21", "fg": "#f0f0f0", "fieldbg": "#2b2d30", "accent": "#4ea1ff"},
        "blue": {"bg": "#dceeff", "fg": "#102030", "fieldbg": "#ffffff", "accent": "#1f6fb2"},
    }
    t = themes.get(name, themes["light"])
    root.configure(bg=t["bg"])
    style.configure("TFrame", background=t["bg"])
    style.configure("TLabel", background=t["bg"], foreground=t["fg"], font=("DejaVu Sans", 12))
    style.configure("TCheckbutton", background=t["bg"], foreground=t["fg"], font=("DejaVu Sans", 12))
    style.configure("TLabelframe", background=t["bg"], foreground=t["fg"], font=("DejaVu Sans", 12, "bold"))
    style.configure("TLabelframe.Label", background=t["bg"], foreground=t["fg"], font=("DejaVu Sans", 12, "bold"))
    style.configure("TButton", font=("DejaVu Sans", 13, "bold"), padding=(14, 10))
    style.configure("TEntry", fieldbackground=t["fieldbg"], padding=6)
    style.configure("TCombobox", padding=6)
    style.map("TButton", foreground=[("active", "white")], background=[("active", t["accent"])])

def set_status(text):
    status_var.set(text)

def ensure_output_dir():
    p = Path(output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p

def unique_path(folder: Path, name: str) -> Path:
    p = Path(name.strip() or DEFAULT_FILENAME)
    if not p.suffix:
        p = p.with_suffix(".mkv")
    base = p.stem
    suffix = p.suffix
    candidate = folder / p.name
    i = 1
    while candidate.exists():
        candidate = folder / f"{base}{i}{suffix}"
        i += 1
    return candidate

def parse_duration():
    h = int(hours_var.get() or 0)
    m = int(minutes_var.get() or 0)
    s = int(seconds_var.get() or 0)
    return f"{h:02d}:{m:02d}:{s:02d}"

def show_chunk(show):
    global chunk_visible
    if show and not chunk_visible:
        chunk_frame.grid()
        chunk_visible = True
    elif not show and chunk_visible:
        chunk_frame.grid_remove()
        chunk_visible = False

def update_chunk_state(*_):
    show_chunk(chunk_var.get())

def show_info():
    win = tk.Toplevel(root)
    win.title("ЧАВО?")
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()

    frm = ttk.Frame(win, padding=14)
    frm.pack(fill="both", expand=True)

    txt = (
        "Запись по кускам — это режим, при котором запись автоматически\n"
        "разбивается на отдельные файлы через заданный промежуток времени.\n\n"
        "Если галочка включена, время куска можно изменить.\n"
        "Если галочка выключена, запись идёт одним непрерывным файлом.\n"
    )
    ttk.Label(frm, text=txt, justify="left").pack(anchor="w")
    ttk.Button(frm, text="ПОНЯЛ", command=win.destroy).pack(pady=(12, 0))

def browse_folder():
    folder = filedialog.askdirectory(
        title="Выбери папку для записей",
        initialdir=output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR
    )
    if folder:
        output_dir_var.set(folder)

def get_audio_sources():
    items = []
    try:
        out = subprocess.check_output(["pactl", "list", "sources", "short"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                items.append(parts[1])
    except Exception:
        pass
    return items or ["default"]

def refresh_lists():
    audio = get_audio_sources()
    audio_combo["values"] = audio
    if audio_var.get() not in audio:
        audio_var.set(audio[0])

def build_cmd(out: Path):
    base = [
        "ffmpeg",
        "-loglevel", "warning",
        "-thread_queue_size", "512",
        "-framerate", "30",
        "-video_size", size_var.get(),
        "-f", "x11grab",
        "-i", DEFAULT_DISPLAY,
        "-thread_queue_size", "512",
        "-f", "pulse",
        "-i", audio_var.get(),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
    ]
    if chunk_var.get():
        base += ["-shortest", "-t", parse_duration()]
    base.append(str(out))
    return base

def start_recording():
    global proc, paused
    if proc and proc.poll() is None:
        messagebox.showinfo("Запись", "Запись уже идёт.")
        return

    folder = ensure_output_dir()
    out = unique_path(folder, name_var.get())
    cmd = build_cmd(out)

    try:
        proc = subprocess.Popen(cmd, start_new_session=True)
    except FileNotFoundError:
        messagebox.showerror("Ошибка", "ffmpeg не найден.")
        return

    paused = False
    set_status(f"Запись: {out.name}")

    def watcher():
        global proc, paused
        proc.wait()
        paused = False
        set_status("Остановлено")

    threading.Thread(target=watcher, daemon=True).start()

def pause_recording():
    global proc, paused
    if not proc or proc.poll() is not None:
        return
    if not paused:
        os.killpg(proc.pid, signal.SIGSTOP)
        paused = True
        set_status("Пауза")

def resume_recording():
    global proc, paused
    if not proc or proc.poll() is not None:
        return
    if paused:
        os.killpg(proc.pid, signal.SIGCONT)
        paused = False
        set_status("Запись")

def stop_recording():
    global proc, paused
    if not proc or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass
    paused = False
    set_status("Остановлено")

def set_theme(*_):
    apply_theme(theme_var.get())

top = ttk.Frame(root, padding=14)
top.pack(fill="both", expand=True)

row1 = ttk.Frame(top)
row1.pack(fill="x", pady=(0, 10))
ttk.Label(row1, text="Как записать файл (имя):").pack(side="left")
name_var = tk.StringVar(value=DEFAULT_FILENAME)
ttk.Entry(row1, textvariable=name_var, width=28).pack(side="left", padx=10)

row2 = ttk.Frame(top)
row2.pack(fill="x", pady=(0, 10))
chunk_var = tk.BooleanVar(value=False)
ttk.Checkbutton(row2, text="Запись по кускам", variable=chunk_var, command=update_chunk_state).pack(side="left")
ttk.Button(row2, text="info", width=6, command=show_info).pack(side="left", padx=8)

row3 = ttk.LabelFrame(top, text="Путь папки для записей", padding=12)
row3.pack(fill="x", pady=(0, 10))
output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
ttk.Entry(row3, textvariable=output_dir_var, width=58).pack(side="left", padx=(0, 10), fill="x", expand=True)
ttk.Button(row3, text="Обзор...", command=browse_folder).pack(side="left")

settings = ttk.LabelFrame(top, text="Настройки", padding=12)
settings.pack(fill="x", pady=(0, 10))

ttk.Label(settings, text="размер записи:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
size_var = tk.StringVar(value="1280x720")
size_combo = ttk.Combobox(
    settings,
    textvariable=size_var,
    values=["1920x1080", "1680x1050", "1280x1024", "1440x900", "1280x800", "1280x720", "1024x768", "800x600", "640x480"],
    width=18,
    state="readonly"
)
size_combo.grid(row=0, column=1, sticky="w", pady=5)

ttk.Label(settings, text="звук:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
audio_var = tk.StringVar()
audio_combo = ttk.Combobox(settings, textvariable=audio_var, width=52, state="readonly")
audio_combo.grid(row=1, column=1, sticky="w", pady=5)

chunk_frame = ttk.Frame(settings)
ttk.Label(chunk_frame, text="время записи на кусок:").grid(row=0, column=0, sticky="w", padx=(0, 8))
dur_box = ttk.Frame(chunk_frame)
dur_box.grid(row=0, column=1, sticky="w")
hours_var = tk.StringVar(value="0")
minutes_var = tk.StringVar(value="2")
seconds_var = tk.StringVar(value="0")
ttk.Spinbox(dur_box, from_=0, to=99, textvariable=hours_var, width=6).pack(side="left")
ttk.Label(dur_box, text="час").pack(side="left", padx=(4, 10))
ttk.Spinbox(dur_box, from_=0, to=59, textvariable=minutes_var, width=6).pack(side="left")
ttk.Label(dur_box, text="мин").pack(side="left", padx=(4, 10))
ttk.Spinbox(dur_box, from_=0, to=59, textvariable=seconds_var, width=6).pack(side="left")
ttk.Label(dur_box, text="сек").pack(side="left", padx=(4, 0))
chunk_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

buttons = ttk.Frame(top)
buttons.pack(fill="x", pady=(6, 0))
ttk.Button(buttons, text="Старт", command=start_recording).pack(side="left", expand=True, fill="x", padx=4)
ttk.Button(buttons, text="Пауза", command=pause_recording).pack(side="left", expand=True, fill="x", padx=4)
ttk.Button(buttons, text="Продолжить", command=resume_recording).pack(side="left", expand=True, fill="x", padx=4)
ttk.Button(buttons, text="Стоп", command=stop_recording).pack(side="left", expand=True, fill="x", padx=4)

theme_row = ttk.Frame(top)
theme_row.pack(fill="x", pady=(10, 0))
ttk.Label(theme_row, text="Тема:").pack(side="left")
theme_var = tk.StringVar(value=DEFAULT_THEME)
theme_combo = ttk.Combobox(theme_row, textvariable=theme_var, values=["light", "dark", "blue"], width=10, state="readonly")
theme_combo.pack(side="left", padx=8)
theme_combo.bind("<<ComboboxSelected>>", set_theme)

status_var = tk.StringVar(value="Готово")
ttk.Label(top, textvariable=status_var).pack(anchor="w", pady=(14, 0))

apply_theme(DEFAULT_THEME)
refresh_lists()
update_chunk_state()
root.protocol("WM_DELETE_WINDOW", lambda: (stop_recording(), root.destroy()))
root.mainloop()
