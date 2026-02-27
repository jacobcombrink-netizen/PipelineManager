"""
Pipeline Manager — Floating Dock
Run with:  pythonw dock.pyw   (no console window)
Or:        python dock.pyw    (with console for debugging)

Requires the Flask app to be running at http://localhost:5000
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import threading
import urllib.request
import urllib.error
import urllib.parse
import json
import subprocess
import os
import sys

API = "http://localhost:5000"

# ── Colour palette ─────────────────────────────────────────────────────────────
BG       = "#020617"
BG2      = "#0f172a"
BG3      = "#1e293b"
BORDER   = "#334155"
TEXT     = "#e2e8f0"
TEXT_DIM = "#64748b"
TEXT_MUT = "#475569"
ACCENT   = "#6366f1"
GREEN    = "#22c55e"
AMBER    = "#f59e0b"
RED      = "#ef4444"
BLUE     = "#3b82f6"

# ── API helpers ────────────────────────────────────────────────────────────────

def api_get(path):
    try:
        req = urllib.request.Request(API + path)
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None

def api_post(path, data=None, json_data=None):
    try:
        if json_data is not None:
            body = json.dumps(json_data).encode()
            req = urllib.request.Request(API + path, data=body,
                                         headers={"Content-Type": "application/json"})
        else:
            body = urllib.parse.urlencode(data or {}).encode()
            req = urllib.request.Request(API + path, data=body)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def copy_to_clipboard(root, text):
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()

# ── Main Dock Window ───────────────────────────────────────────────────────────

class PipelineDock(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pipeline Dock")
        self.geometry("360x620+20+40")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(300, 400)

        # Always on top
        self.wm_attributes("-topmost", True)

        # Remove default titlebar chrome on Windows, add custom drag bar
        self.overrideredirect(True)
        self._drag_x = 0
        self._drag_y = 0

        self.selected_job = None   # dict
        self.jobs_cache   = []
        self.prompts_cache = []

        self._build_ui()
        self._poll_connection()

    # ── Drag support (since we removed the titlebar) ───────────────────────────

    def _start_drag(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _do_drag(self, e):
        self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        bar = tk.Frame(self, bg=BG2, height=32)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar.bind("<ButtonPress-1>",   self._start_drag)
        bar.bind("<B1-Motion>",       self._do_drag)

        tk.Label(bar, text="🚀  Pipeline Dock", bg=BG2,
                 fg=ACCENT, font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)

        self.conn_dot = tk.Label(bar, text="●", bg=BG2, fg=RED, font=("Segoe UI", 9))
        self.conn_dot.pack(side="right", padx=4)

        tk.Button(bar, text="×", bg=BG2, fg=TEXT_DIM, bd=0, padx=8,
                  activebackground=BG3, activeforeground=RED,
                  font=("Segoe UI", 11), command=self.destroy).pack(side="right")

        tk.Button(bar, text="–", bg=BG2, fg=TEXT_DIM, bd=0, padx=8,
                  activebackground=BG3, activeforeground=TEXT,
                  font=("Segoe UI", 11), command=self._minimize).pack(side="right")

        tk.Button(bar, text="⊞", bg=BG2, fg=TEXT_DIM, bd=0, padx=8,
                  activebackground=BG3, activeforeground=TEXT,
                  font=("Segoe UI", 10),
                  command=lambda: self.wm_attributes("-topmost", not self.wm_attributes("-topmost"))
                  ).pack(side="right", padx=0)

        # Notebook (tabs)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dock.TNotebook",       background=BG,  borderwidth=0, tabmargins=0)
        style.configure("Dock.TNotebook.Tab",   background=BG2, foreground=TEXT_DIM,
                        padding=[10, 4], font=("Segoe UI", 8))
        style.map("Dock.TNotebook.Tab",
                  background=[("selected", BG3)],
                  foreground=[("selected", ACCENT)])

        self.nb = ttk.Notebook(self, style="Dock.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_jobs_tab()
        self._build_prompts_tab()
        self._build_submit_tab()
        self._build_links_tab()

    def _minimize(self):
        self.overrideredirect(False)
        self.iconify()
        self.bind("<Map>", self._on_restore)

    def _on_restore(self, e):
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.unbind("<Map>")

    # ── Jobs Tab ───────────────────────────────────────────────────────────────

    def _build_jobs_tab(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="Jobs")

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=8, pady=(6,4))

        tk.Label(top, text="Project filter:", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack(side="left")

        self.project_var = tk.StringVar(value="")
        self.project_combo = ttk.Combobox(top, textvariable=self.project_var,
                                          state="readonly", width=16,
                                          font=("Segoe UI", 8))
        self.project_combo.pack(side="left", padx=(4,0))
        self.project_combo.bind("<<ComboboxSelected>>", lambda e: self._load_jobs())

        tk.Button(top, text="⟳", bg=BG2, fg=ACCENT, bd=0, padx=6,
                  font=("Segoe UI", 10), activebackground=BG3,
                  command=self._load_jobs).pack(side="right")

        # Job list
        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True, padx=(8,0), pady=(0,8))

        self.jobs_frame = tk.Frame(canvas, bg=BG)
        self.jobs_win = canvas.create_window((0,0), window=self.jobs_frame, anchor="nw")
        self.jobs_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(self.jobs_win, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self.jobs_canvas = canvas
        self.jobs_status = tk.Label(f, text="Not connected", bg=BG, fg=TEXT_MUT,
                                    font=("Segoe UI", 8))
        self.jobs_status.pack(pady=2)

    def _load_jobs(self):
        def fetch():
            # Load projects for combo
            projects = api_get("/projects") or []
            # Load jobs
            pid = ""
            for p in (projects if isinstance(projects, list) else []):
                if p.get("name") == self.project_var.get():
                    pid = str(p["id"])
                    break
            url = "/api/dock/jobs" + (f"?project_id={pid}" if pid else "")
            jobs = api_get(url) or []
            self.jobs_cache = jobs if isinstance(jobs, list) else []

            self.after(0, lambda: self._render_jobs(self.jobs_cache))
            if isinstance(projects, list):
                names = [""] + [p["name"] for p in projects]
                self.after(0, lambda: self.project_combo.configure(values=names))

        threading.Thread(target=fetch, daemon=True).start()

    def _render_jobs(self, jobs):
        for w in self.jobs_frame.winfo_children():
            w.destroy()

        if not jobs:
            tk.Label(self.jobs_frame, text="No outstanding jobs.",
                     bg=BG, fg=TEXT_MUT, font=("Segoe UI", 8)).pack(pady=8)
            self.jobs_status.config(text=f"{len(jobs)} jobs")
            return

        for job in jobs:
            self._job_card(self.jobs_frame, job)

        self.jobs_status.config(text=f"{len(jobs)} jobs")

    def _job_card(self, parent, job):
        is_sel = self.selected_job and self.selected_job["id"] == job["id"]
        border_col = ACCENT if is_sel else BORDER

        outer = tk.Frame(parent, bg=border_col, padx=1, pady=1)
        outer.pack(fill="x", pady=2)

        inner = tk.Frame(outer, bg=BG2, cursor="hand2")
        inner.pack(fill="x")

        status_colours = {"planned": TEXT_MUT, "in_progress": AMBER,
                          "rendered": GREEN, "complete": GREEN}
        dot_col = status_colours.get(job.get("status",""), TEXT_MUT)

        tk.Label(inner, text="●", bg=BG2, fg=dot_col,
                 font=("Segoe UI", 7)).pack(side="left", padx=(6,2), pady=6)

        info = tk.Frame(inner, bg=BG2)
        info.pack(side="left", fill="x", expand=True, pady=4)

        char = job.get("character_name") or "(no character)"
        ot   = job.get("output_type_name") or "—"
        tk.Label(info, text=char, bg=BG2, fg=TEXT,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(info, text=f"{ot}  ·  #{job['id']}  ·  {job.get('status','')}",
                 bg=BG2, fg=TEXT_DIM, font=("Segoe UI", 7), anchor="w").pack(fill="x")

        def select(j=job, o=outer):
            self.selected_job = j
            self._render_jobs(self.jobs_cache)
            self._update_submit_label()
            self._load_prompts(j["id"])
            self.nb.select(1)  # switch to prompts

        for w in (outer, inner, info):
            w.bind("<Button-1>", lambda e, fn=select: fn())
        for child in info.winfo_children():
            child.bind("<Button-1>", lambda e, fn=select: fn())

    # ── Prompts Tab ────────────────────────────────────────────────────────────

    def _build_prompts_tab(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="Prompts")

        self.prompts_label = tk.Label(f, text="Select a job to see prompts",
                                      bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8))
        self.prompts_label.pack(pady=(6,4), padx=8, anchor="w")

        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True, padx=(8,0))

        self.prompts_frame = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0,0), window=self.prompts_frame, anchor="nw")
        self.prompts_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(win, width=e.width))

    def _load_prompts(self, job_id):
        def fetch():
            prompts = api_get(f"/api/dock/job-prompts/{job_id}") or []
            self.prompts_cache = prompts if isinstance(prompts, list) else []
            self.after(0, self._render_prompts)

        threading.Thread(target=fetch, daemon=True).start()

    def _render_prompts(self):
        for w in self.prompts_frame.winfo_children():
            w.destroy()

        job_name = ""
        if self.selected_job:
            job_name = (self.selected_job.get("character_name") or "") + " #" + str(self.selected_job["id"])
        self.prompts_label.config(text=f"Prompts: {job_name}" if job_name else "Select a job")

        if not self.prompts_cache:
            tk.Label(self.prompts_frame, text="No prompts linked to this job.",
                     bg=BG, fg=TEXT_MUT, font=("Segoe UI", 8),
                     wraplength=300, justify="left").pack(pady=8, padx=4)
            return

        for p in self.prompts_cache:
            self._prompt_card(self.prompts_frame, p)

    def _prompt_card(self, parent, prompt):
        status = prompt.get("status", "pending")
        bar_colours = {"pending": BG3, "collected": BLUE,
                       "done": GREEN, "flagged": RED}
        text_colours = {"pending": TEXT, "collected": "#93c5fd",
                        "done": TEXT_MUT, "flagged": "#fca5a5"}

        outer = tk.Frame(parent, bg=bar_colours.get(status, BG3), padx=2, pady=0)
        outer.pack(fill="x", pady=2)

        inner = tk.Frame(outer, bg=BG2)
        inner.pack(fill="x")

        # Label row
        if prompt.get("label"):
            tk.Label(inner, text=prompt["label"].upper(), bg=BG2,
                     fg=TEXT_MUT, font=("Segoe UI", 7)).pack(anchor="w", padx=6, pady=(4,0))

        # Prompt text (click to copy)
        txt_col = text_colours.get(status, TEXT)
        ptext = prompt.get("text","")
        preview = ptext[:120] + ("…" if len(ptext) > 120 else "")

        txt_lbl = tk.Label(inner, text=preview, bg=BG2, fg=txt_col,
                           font=("Segoe UI", 8), wraplength=280, justify="left",
                           cursor="hand2")
        txt_lbl.pack(anchor="w", padx=6, pady=(2,4))

        # Strikethrough simulation for done
        if status == "done":
            txt_lbl.config(font=("Segoe UI", 8, "overstrike"))

        # Action buttons row
        btn_row = tk.Frame(inner, bg=BG2)
        btn_row.pack(fill="x", padx=6, pady=(0,5))

        pid = prompt["id"]

        def make_btn(parent, text, tooltip, fg, cmd):
            b = tk.Button(parent, text=text, bg=BG3, fg=fg, bd=0,
                          padx=5, pady=1, font=("Segoe UI", 8),
                          activebackground=BORDER, activeforeground=TEXT,
                          cursor="hand2", command=cmd)
            b.pack(side="left", padx=2)
            return b

        def do_copy(pid=pid, txt=ptext, lbl=txt_lbl):
            copy_to_clipboard(self, txt)
            # Set collected if pending
            if prompt.get("status") == "pending":
                self._set_prompt_status(pid, "collected")
            self._toast("Copied!")

        def do_done(pid=pid):
            self._set_prompt_status(pid, "done")

        def do_reset(pid=pid):
            self._set_prompt_status(pid, "pending")

        def do_flag(pid=pid):
            self._set_prompt_status(pid, "flagged")

        make_btn(btn_row, "📋 Copy", "Copy to clipboard", TEXT,   do_copy)
        make_btn(btn_row, "✓",      "Mark done",          GREEN,  do_done)
        make_btn(btn_row, "↺",      "Reset",              TEXT_DIM, do_reset)
        make_btn(btn_row, "!",      "Flag for revision",  RED,    do_flag)

    def _set_prompt_status(self, pid, status):
        def do():
            api_post(f"/api/prompts/status/{pid}", json_data={"status": status})
            if self.selected_job:
                self.after(100, lambda: self._load_prompts(self.selected_job["id"]))
        threading.Thread(target=do, daemon=True).start()

    # ── Submit Tab ─────────────────────────────────────────────────────────────

    def _build_submit_tab(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="Submit")

        self.submit_job_label = tk.Label(f, text="No job selected",
                                         bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8),
                                         wraplength=320, justify="left")
        self.submit_job_label.pack(padx=10, pady=(10,4), anchor="w")

        # Drop zone
        self.drop_frame = tk.Frame(f, bg=BG2, relief="flat", bd=0)
        self.drop_frame.pack(fill="x", padx=10, pady=4)

        self.drop_label = tk.Label(self.drop_frame,
                                   text="Click to browse for a file\n(video or image)",
                                   bg=BG2, fg=TEXT_MUT,
                                   font=("Segoe UI", 9), pady=24, cursor="hand2")
        self.drop_label.pack(fill="x")

        self.drop_frame.config(highlightbackground=BORDER,
                               highlightthickness=1, highlightcolor=ACCENT)

        self.drop_label.bind("<Button-1>", self._browse_file)
        self.drop_frame.bind("<Button-1>", self._browse_file)

        self.file_label = tk.Label(f, text="", bg=BG, fg=TEXT_DIM,
                                   font=("Segoe UI", 7), wraplength=320)
        self.file_label.pack(padx=10, anchor="w")

        self.selected_file = ""

        self.submit_btn = tk.Button(f, text="Submit & Mark Job Complete",
                                    bg=BG3, fg=TEXT_MUT,
                                    font=("Segoe UI", 9, "bold"),
                                    bd=0, pady=8, state="disabled",
                                    cursor="hand2",
                                    command=self._submit_media)
        self.submit_btn.pack(fill="x", padx=10, pady=8)

        note = ("The job will be marked Complete.\n"
                "A media asset will be created with metadata\npre-filled from the job.")
        tk.Label(f, text=note, bg=BG, fg=TEXT_MUT,
                 font=("Segoe UI", 8), justify="left").pack(padx=10, anchor="w")

        # Open in browser shortcut
        tk.Button(f, text="Open Media Library in browser →",
                  bg=BG, fg=ACCENT, bd=0, font=("Segoe UI", 8),
                  cursor="hand2",
                  command=lambda: self._open_browser("/media")).pack(padx=10, pady=(16,4), anchor="w")

    def _update_submit_label(self):
        if self.selected_job:
            char = self.selected_job.get("character_name") or "(no character)"
            ot   = self.selected_job.get("output_type_name") or "—"
            self.submit_job_label.config(
                text=f"Job #{self.selected_job['id']}  ·  {char}  ·  {ot}",
                fg=ACCENT)
        else:
            self.submit_job_label.config(text="No job selected — pick one in the Jobs tab",
                                         fg=TEXT_DIM)
        self._check_submit_ready()

    def _browse_file(self, event=None):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select rendered output",
            filetypes=[("Media files", "*.mp4 *.mov *.avi *.mkv *.png *.jpg *.jpeg *.webp"),
                       ("All files", "*.*")])
        if path:
            self.selected_file = path
            short = os.path.basename(path)
            self.drop_label.config(text=f"✓  {short}", fg=GREEN)
            self.file_label.config(text=path)
            self.drop_frame.config(highlightbackground=GREEN)
            self._check_submit_ready()

    def _check_submit_ready(self):
        ready = bool(self.selected_job and self.selected_file)
        self.submit_btn.config(
            state="normal" if ready else "disabled",
            bg=ACCENT if ready else BG3,
            fg=TEXT if ready else TEXT_MUT,
            cursor="hand2" if ready else "arrow")

    def _submit_media(self):
        if not self.selected_job or not self.selected_file:
            return
        self.submit_btn.config(text="Submitting…", state="disabled", bg=BG3)

        def do():
            result = api_post("/api/dock/submit-media", {
                "job_id": str(self.selected_job["id"]),
                "file_path": self.selected_file
            })
            self.after(0, lambda: self._on_submit_done(result))

        threading.Thread(target=do, daemon=True).start()

    def _on_submit_done(self, result):
        if result and result.get("ok"):
            title = result.get("title", "")
            self._toast(f"Submitted: {title or 'done'}")
            self.selected_job = None
            self.selected_file = ""
            self.drop_label.config(text="Click to browse for a file\n(video or image)",
                                   fg=TEXT_MUT)
            self.file_label.config(text="")
            self.drop_frame.config(highlightbackground=BORDER)
            self.submit_btn.config(text="Submit & Mark Job Complete")
            self._update_submit_label()
            self._load_jobs()
        else:
            self._toast("Error — is the server running?")
            self.submit_btn.config(text="Submit & Mark Job Complete",
                                   state="normal", bg=ACCENT, fg=TEXT)

    # ── Links Tab ──────────────────────────────────────────────────────────────

    def _build_links_tab(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="Links")

        self.links_frame = f
        self._render_links()

    def _render_links(self):
        for w in self.links_frame.winfo_children():
            w.destroy()

        tk.Label(self.links_frame, text="Quick access — opens in browser",
                 bg=BG, fg=TEXT_MUT, font=("Segoe UI", 8)).pack(pady=(8,4), padx=10, anchor="w")

        def fetch():
            config = api_get("/api/dock/config") or []
            # fall back to hardcoded defaults if endpoint not ready
            if not config:
                config = [
                    {"label": "Dashboard",    "url": "/"},
                    {"label": "Job Builder",  "url": "/jobs/builder"},
                    {"label": "Render Jobs",  "url": "/jobs"},
                    {"label": "Media Library","url": "/media"},
                    {"label": "Journal",      "url": "/journal"},
                    {"label": "Projects",     "url": "/projects"},
                    {"label": "Archetypes",   "url": "/archetypes"},
                    {"label": "Characters",   "url": "/characters"},
                    {"label": "Ingredients",  "url": "/ingredients"},
                    {"label": "Output Types", "url": "/output-types"},
                    {"label": "Top Layer",    "url": "/top-layer"},
                    {"label": "Prompt Library","url": "/prompt-library"},
                    {"label": "Data Manager", "url": "/data"},
                ]
            self.after(0, lambda: self._render_link_buttons(config))

        threading.Thread(target=fetch, daemon=True).start()

    def _render_link_buttons(self, config):
        for w in self.links_frame.winfo_children():
            if isinstance(w, tk.Button):
                w.destroy()

        for item in config:
            label = item.get("label","")
            url   = item.get("url","")
            if not label or not url:
                continue
            full_url = url if url.startswith("http") else API + url
            tk.Button(self.links_frame, text=label,
                      bg=BG2, fg=TEXT, bd=0, pady=7,
                      font=("Segoe UI", 9), anchor="w", padx=14,
                      activebackground=BG3, activeforeground=ACCENT,
                      cursor="hand2",
                      command=lambda u=full_url: self._open_browser(u)
                      ).pack(fill="x", padx=10, pady=1)

    def _open_browser(self, url):
        full = url if url.startswith("http") else API + url
        import webbrowser
        webbrowser.open(full)

    # ── Connection polling ─────────────────────────────────────────────────────

    def _poll_connection(self):
        def check():
            result = api_get("/api/dock/jobs")
            connected = result is not None
            colour = GREEN if connected else RED
            status  = "●  Connected" if connected else "●  Server offline"
            self.after(0, lambda: self.conn_dot.config(fg=colour, text=status))
            if connected and not self.jobs_cache:
                self.after(0, self._load_jobs)
        threading.Thread(target=check, daemon=True).start()
        self.after(8000, self._poll_connection)

    # ── Toast notification ─────────────────────────────────────────────────────

    def _toast(self, message):
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.wm_attributes("-topmost", True)
        toast.configure(bg=ACCENT)

        tk.Label(toast, text=message, bg=ACCENT, fg="white",
                 font=("Segoe UI", 9), padx=14, pady=8).pack()

        # Position below the dock
        self.update_idletasks()
        x = self.winfo_x()
        y = self.winfo_y() + self.winfo_height() + 4
        toast.geometry(f"+{x}+{y}")
        toast.after(2000, toast.destroy)


# ── Add a dock config API endpoint ────────────────────────────────────────────
# The dock falls back to full app links if this 404s, so no change needed to
# Flask — but we do need to expose the dock config. We patch this by just
# hardcoding all app pages in the Links tab above.

def add_dock_api():
    """Monkey-patch: expose /api/dock/config by reading from Flask if possible."""
    pass  # handled gracefully in _render_links fallback


if __name__ == "__main__":
    app = PipelineDock()
    app.mainloop()
