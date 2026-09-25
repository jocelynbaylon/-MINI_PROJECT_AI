"""
gui_app.py
----------
Desktop front-end for the OBE Syllabus Generator microservice.

Course dropdown -> input fields (Instructor / Section / School Year / Semester)
-> [Generate Syllabus] (LLM engine -> Pydantic validation -> SQLite)
-> [Download HTML] / [Print] / [Download DOCX]
"""

import os
import sys
import platform
import subprocess
import threading
import queue
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterweb import HtmlFrame

import db_manager
import export_engine
from llm_engine import generate_course_syllabus, is_mock_mode, warm_up_model
from mock_data import COURSES

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

APP_DIR = os.path.dirname(__file__)
OUT_DIR = os.path.join(APP_DIR, "exports")
os.makedirs(OUT_DIR, exist_ok=True)


class RoundedFrame(tk.Canvas):
    def __init__(self, parent, bg_color, corner_radius=12, expand_content=False, **kwargs):
        tk.Canvas.__init__(self, parent, bg=parent["bg"], highlightthickness=0, **kwargs)
        self.corner_radius = corner_radius
        self.bg_color = bg_color
        self.expand_content = expand_content
        
        self.container = tk.Frame(self, bg=bg_color)
        self.window_id = self.create_window(0, 0, window=self.container, anchor="nw")
        
        self.bind("<Configure>", self._on_resize)
        self.container.bind("<Configure>", self._on_frame_resize)
        
    def _on_frame_resize(self, event):
        # Only update canvas height if it's different, to avoid loop
        if int(self.cget("height")) != event.height:
            self.configure(height=event.height)
        
    def _on_resize(self, event):
        self.delete("bg")
        w = event.width
        h = event.height
        d = self.corner_radius * 2
        if w < d or h < d: return
        
        self.create_oval(0, 0, d, d, fill=self.bg_color, outline=self.bg_color, tags="bg")
        self.create_oval(w-d, 0, w, d, fill=self.bg_color, outline=self.bg_color, tags="bg")
        self.create_oval(0, h-d, d, h, fill=self.bg_color, outline=self.bg_color, tags="bg")
        self.create_oval(w-d, h-d, w, h, fill=self.bg_color, outline=self.bg_color, tags="bg")
        
        self.create_rectangle(self.corner_radius, 0, w-self.corner_radius, h, fill=self.bg_color, outline=self.bg_color, tags="bg")
        self.create_rectangle(0, self.corner_radius, w, h-self.corner_radius, fill=self.bg_color, outline=self.bg_color, tags="bg")
        self.tag_lower("bg")
        
        if self.expand_content:
            self.itemconfigure(self.window_id, width=w, height=h)
        else:
            self.itemconfigure(self.window_id, width=w)


class OBEApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI-Powered OBE Syllabus Generator - CCS")
        self.geometry("900x700")
        self.minsize(820, 600)
        self.configure(bg="#f4f0ec")
        self.last_export_path = None
        
        style = ttk.Style(self)
        try: style.theme_use('clam')
        except: pass
        style.configure("Treeview", background="#ffffff", foreground="#333333", rowheight=32, 
                        fieldbackground="#ffffff", borderwidth=0, font=("Segoe UI", 10))
        style.map("Treeview", background=[('selected', '#8A1538')], foreground=[('selected', 'white')])
        style.configure("Treeview.Heading", background="#f4f0ec", foreground="#8A1538", 
                        font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.configure("TProgressbar", background="#D4AF37", thickness=12)
        
        # Modern thin scrollbar without arrows
        style.layout('Vertical.TScrollbar', 
            [('Vertical.Scrollbar.trough', 
                {'children': [('Vertical.Scrollbar.thumb', 
                               {'expand': '1', 'sticky': 'nswe'})],
                 'sticky': 'ns'})])
        style.configure("Vertical.TScrollbar", 
                     background="#cccccc", 
                     troughcolor="#ffffff", 
                     bordercolor="#ffffff",
                     lightcolor="#cccccc",
                     darkcolor="#cccccc",
                     relief="flat")
        style.configure("TCombobox", 
                        background="#f9f9f9", 
                        fieldbackground="#f9f9f9", 
                        bordercolor="#e0dcd9", 
                        arrowcolor="#8A1538",
                        relief="flat")
        self.option_add('*TCombobox*Listbox.font', ("Segoe UI", 10))
        self.option_add('*TCombobox*Listbox.background', "#ffffff")
        self.option_add('*TCombobox*Listbox.foreground', "#333333")
        self.option_add('*TCombobox*Listbox.selectBackground', "#8A1538")
        
        self.current_course_code = None
        self._generating = False
        self._gen_queue = queue.Queue()

        db_manager.init_db()
        self._build_header()
        self._build_form()
        self._build_actions()
        self._build_records()
        self._build_log()
        self.refresh_records()

        # The window is shown right away; the LLM-backend reachability check
        # (a network call) happens off the main thread so it never delays
        # startup. Generation itself will still work correctly meanwhile --
        # is_mock_mode() blocks only the background thread, not the UI.
        self._log(f"Ready. Database: {db_manager.DB_PATH}")
        self._log("Checking LLM backend (Ollama)...")
        threading.Thread(target=self._detect_mode, daemon=True).start()

    def _detect_mode(self):
        mock = is_mock_mode()
        mode = "OFFLINE (mock generator)" if mock else "LIVE (Ollama/Qwen)"
        self.after(0, lambda: self._log(f"LLM mode: {mode}"))
        if not mock:
            # Preload the model into memory now (kept warm via keep_alive) so
            # the first real "Generate Syllabus" click doesn't also have to
            # pay the model-load cost on top of actual generation time.
            self.after(0, lambda: self._log("Warming up Ollama model..."))
            warm_up_model()
            self.after(0, lambda: self._log("[OK] Model warmed up and ready."))

    # ---------- UI construction ----------
    def _build_header(self):
        header = tk.Frame(self, bg="#7a0c1e", height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        logo_path = os.path.join(APP_DIR, "uphsd.png")
        ccs_logo_path = os.path.join(APP_DIR, "ccs.png")
        
        if HAS_PIL and os.path.exists(logo_path):
            img = Image.open(logo_path).resize((44, 44))
            self._logo_img = ImageTk.PhotoImage(img)
            tk.Label(header, image=self._logo_img, bg="#7a0c1e", bd=0).pack(side="left", padx=(12, 0))
            
        if HAS_PIL and os.path.exists(ccs_logo_path):
            img2 = Image.open(ccs_logo_path).resize((44, 44))
            self._ccs_logo_img = ImageTk.PhotoImage(img2)
            tk.Label(header, image=self._ccs_logo_img, bg="#7a0c1e", bd=0).pack(side="left", padx=(2, 12))
            
        tk.Label(header, text="College of Computer Studies — OBE Syllabus Generator",
                 fg="#FFD700", bg="#7a0c1e", font=("Segoe UI", 14, "bold")).pack(side="left", pady=12)

    def _build_form(self):
        card_wrap = tk.Frame(self, bg="#f4f0ec")
        card_wrap.pack(fill="x", padx=20, pady=(15, 5))
        
        rounded_card = RoundedFrame(card_wrap, bg_color="#ffffff", corner_radius=15)
        rounded_card.pack(fill="x")
        panel = rounded_card.container
        
        title = tk.Label(panel, text="Course & Class Details", bg="#ffffff", fg="#8A1538", font=("Segoe UI", 12, "bold"))
        title.grid(row=0, column=0, columnspan=6, sticky="w", padx=10, pady=(10, 15))

        labels = ["Course", "Course Code", "Instructor", "Section", "School Year", "Semester"]
        for i, text in enumerate(labels):
            tk.Label(panel, text=text, bg="#ffffff", fg="#555555", font=("Segoe UI", 10, "bold")).grid(
                row=(i // 3) + 1, column=(i % 3) * 2, sticky="w", padx=(10, 4), pady=8)

        self.course_var = tk.StringVar()
        self.course_map = {v["title"]: k for k, v in COURSES.items()}
        course_combo = ttk.Combobox(panel, textvariable=self.course_var, state="readonly",
                                     values=list(self.course_map.keys()), width=32, font=("Segoe UI", 10))
        course_combo.current(0)
        course_combo.grid(row=1, column=1, padx=4, pady=8, sticky="ew")
        course_combo.bind("<<ComboboxSelected>>", self._on_course_change)

        self.code_var = tk.StringVar()
        tk.Entry(panel, textvariable=self.code_var, width=18, font=("Segoe UI", 10), relief="flat", bg="#f9f9f9", highlightthickness=1, highlightbackground="#e0dcd9").grid(row=1, column=3, padx=4, pady=8)

        self.instructor_var = tk.StringVar(value="(Instructor Name)")
        tk.Entry(panel, textvariable=self.instructor_var, width=22, font=("Segoe UI", 10), relief="flat", bg="#f9f9f9", highlightthickness=1, highlightbackground="#e0dcd9").grid(row=1, column=5, padx=4, pady=8)

        self.section_var = tk.StringVar(value="(Section)")
        tk.Entry(panel, textvariable=self.section_var, width=18, font=("Segoe UI", 10), relief="flat", bg="#f9f9f9", highlightthickness=1, highlightbackground="#e0dcd9").grid(row=2, column=1, padx=4, pady=8)

        self.sy_var = tk.StringVar(value="2026-2027")
        tk.Entry(panel, textvariable=self.sy_var, width=18, font=("Segoe UI", 10), relief="flat", bg="#f9f9f9", highlightthickness=1, highlightbackground="#e0dcd9").grid(row=2, column=3, padx=4, pady=8)

        self.sem_var = tk.StringVar(value="1st Semester")
        sem_combo = ttk.Combobox(panel, textvariable=self.sem_var, state="readonly",
                     values=["1st Semester", "2nd Semester"], width=16, font=("Segoe UI", 10))
        sem_combo.grid(row=2, column=5, padx=4, pady=8)
        self._on_course_change()

    def _build_actions(self):
        bar = tk.Frame(self, bg="#f4f0ec")
        bar.pack(fill="x", padx=20, pady=6)
        
        btn_font = ("Segoe UI", 10, "bold")
        
        self.generate_btn = tk.Button(bar, text="⚙ Generate Syllabus", bg="#8A1538", fg="white",
                                       font=btn_font, relief="flat", padx=10, pady=4, cursor="hand2",
                                       command=self.on_generate)
        self.generate_btn.pack(side="left", padx=4)
        
        self.stop_btn = tk.Button(bar, text="⏹ Stop", bg="#555555", fg="white", 
                                  font=btn_font, relief="flat", padx=10, pady=4, cursor="hand2",
                                  command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        
        tk.Button(bar, text="⬇ HTML", bg="#ffffff", fg="#333333", font=btn_font, relief="flat", padx=10, pady=4, highlightthickness=1, highlightbackground="#e0dcd9", cursor="hand2", command=self.on_download_html).pack(side="left", padx=4)
        tk.Button(bar, text="🖨 Print", bg="#ffffff", fg="#333333", font=btn_font, relief="flat", padx=10, pady=4, highlightthickness=1, highlightbackground="#e0dcd9", cursor="hand2", command=self.on_print).pack(side="left", padx=4)
        tk.Button(bar, text="📄 DOCX", bg="#105e26", fg="white", font=btn_font, relief="flat", padx=10, pady=4, cursor="hand2", command=self.on_download_docx).pack(side="left", padx=4)
        
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=130)
        self.progress.pack(side="left", padx=12)

    def _build_records(self):
        card_wrap = tk.Frame(self, bg="#f4f0ec")
        card_wrap.pack(fill="both", expand=True, padx=20, pady=(5, 5))
        
        rounded_card = RoundedFrame(card_wrap, bg_color="#ffffff", corner_radius=15, expand_content=True)
        rounded_card.pack(fill="both", expand=True)
        frame = rounded_card.container
        
        title = tk.Label(frame, text="Saved Syllabuses & Preview", bg="#ffffff", fg="#8A1538", font=("Segoe UI", 12, "bold"))
        title.pack(anchor="w", padx=10, pady=(10, 0))

        self.paned = ttk.PanedWindow(frame, orient="horizontal")
        self.paned.pack(fill="both", expand=True, padx=10, pady=10)

        left_panel = tk.Frame(self.paned, bg="#ffffff")
        self.paned.add(left_panel, weight=1)

        self.right_panel = tk.Frame(self.paned, bg="#ffffff")
        self.paned.add(self.right_panel, weight=1)

        table_area = tk.Frame(left_panel, bg="#ffffff")
        table_area.pack(fill="both", expand=True)

        columns = ("code", "title", "instructor", "section", "sy", "sem", "saved")
        headings = {
            "code": ("Course Code", 90),
            "title": ("Course Title", 200),
            "instructor": ("Instructor", 100),
            "section": ("Section", 70),
            "sy": ("School Year", 80),
            "sem": ("Semester", 80),
            "saved": ("Date Saved", 120),
        }
        self.records_tree = ttk.Treeview(table_area, columns=columns, show="headings",
                                          height=7, selectmode="extended")
        for col, (text, width) in headings.items():
            self.records_tree.heading(col, text=text)
            self.records_tree.column(col, width=width, anchor="w")

        vsb = ttk.Scrollbar(table_area, orient="vertical", command=self.records_tree.yview)
        self.records_tree.configure(yscrollcommand=vsb.set)
        self.records_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self.records_tree.bind("<Double-1>", lambda e: self.on_preview_selected())
        self.records_tree.bind("<<TreeviewSelect>>", self._on_record_select)

        btns = tk.Frame(left_panel, bg="#ffffff")
        btns.pack(fill="x", pady=(10, 0))
        btn_font = ("Segoe UI", 9)
        tk.Button(btns, text="🔍 Preview", font=btn_font, bg="#f9f9f9", fg="#333", relief="flat", highlightthickness=1, highlightbackground="#e0dcd9", cursor="hand2", command=self.on_preview_selected).pack(side="left", padx=4)
        tk.Button(btns, text="☑ Select All", font=btn_font, bg="#f9f9f9", fg="#333", relief="flat", highlightthickness=1, highlightbackground="#e0dcd9", cursor="hand2", command=self.on_select_all).pack(side="left", padx=4)
        tk.Button(btns, text="🔄 Refresh", font=btn_font, bg="#f9f9f9", fg="#333", relief="flat", highlightthickness=1, highlightbackground="#e0dcd9", cursor="hand2", command=self.refresh_records).pack(side="left", padx=4)
        tk.Button(btns, text="🗑 Delete", font=btn_font, bg="#8A1538", fg="white", relief="flat", cursor="hand2", command=self.on_delete_selected).pack(side="left", padx=4)

        self.preview_frame = None
        self.preview_lbl = tk.Label(self.right_panel, text="Select a syllabus and click Preview", bg="#ffffff", fg="#888888", font=("Segoe UI", 10))
        self.preview_lbl.pack(expand=True)

    def refresh_records(self):
        """Reloads the Saved Syllabuses table from the database, newest first."""
        for row in self.records_tree.get_children():
            self.records_tree.delete(row)
        try:
            for c in db_manager.list_courses():
                self.records_tree.insert(
                    "", "end", iid=c["course_code"],
                    values=(
                        c["course_code"], c["course_title"], c.get("instructor") or "",
                        c.get("section") or "", c.get("school_year") or "",
                        c.get("semester") or "", c.get("created_at") or "",
                    ),
                )
        except Exception as e:
            self._log(f"[ERROR] Could not load saved syllabuses: {e}")

    def _on_record_select(self, event=None):
        sel = self.records_tree.selection()
        if sel:
            self.current_course_code = sel[0]

    def on_select_all(self):
        for item in self.records_tree.get_children():
            self.records_tree.selection_add(item)

    def on_preview_selected(self):
        sel = self.records_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a syllabus from the list first.")
            return
        code = sel[0]
        self.current_course_code = code
        self._preview_in_browser(code)

    def on_delete_selected(self):
        sel = self.records_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a syllabus from the list first.")
            return
        if not messagebox.askyesno("Confirm delete", f"Delete {len(sel)} saved syllabus(es)?\nThis cannot be undone."):
            return
        try:
            for code in sel:
                db_manager.delete_course(code)
                if self.current_course_code == code:
                    self.current_course_code = None
            self._log(f"[OK] Deleted {len(sel)} record(s) from database.")
            self.refresh_records()
            if self.preview_frame:
                self.preview_frame.destroy()
                self.preview_frame = None
                self.preview_lbl.pack(expand=True)
        except Exception as e:
            self._log(f"[ERROR] Could not delete: {e}")

    def _build_log(self):
        card_wrap = tk.Frame(self, bg="#f4f0ec")
        card_wrap.pack(fill="x", padx=20, pady=(5, 15))
        
        rounded_card = RoundedFrame(card_wrap, bg_color="#ffffff", corner_radius=15)
        rounded_card.pack(fill="x")
        card = rounded_card.container
        
        title = tk.Label(card, text="Activity Log", bg="#ffffff", fg="#8A1538", font=("Segoe UI", 10, "bold"))
        title.pack(anchor="w", padx=10, pady=(5, 0))
        
        self.log_text = tk.Text(card, state="disabled", wrap="word", bg="#1e1e1e", fg="#dcdcdc",
                                 font=("Consolas", 9), height=5, relief="flat", padx=10, pady=10)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_course_change(self, event=None):
        key = self.course_map[self.course_var.get()]
        self.code_var.set(COURSES[key]["default_code"])

    # ---------- actions ----------
    def on_generate(self):
        if self._generating:
            return  # already running -- ignore accidental double-click

        key = self.course_map[self.course_var.get()]
        code = self.code_var.get().strip() or COURSES[key]["default_code"]
        instructor = self.instructor_var.get()
        section = self.section_var.get()
        school_year = self.sy_var.get()
        semester = self.sem_var.get()

        self._generating = True
        self.generate_btn.configure(state="disabled", text="⏳ Generating")
        self.stop_btn.configure(state="normal")
        self.progress.start(12)
        self._log(f"Generating syllabus for {code} ({COURSES[key]['title']})...")

        self._anim_count = 0
        self._animate_btn()

        # The Ollama call (and any DB write) runs on a background thread so the
        # window stays responsive instead of freezing for the whole request;
        # the main thread just polls a queue for the result.
        threading.Thread(
            target=self._generate_worker,
            args=(key, code, instructor, section, school_year, semester),
            daemon=True,
        ).start()
        self.after(100, self._poll_generate_queue)

    def on_stop(self):
        if self._generating:
            import llm_engine
            llm_engine.cancel_generation()
            self._log("Stopping generation...")
            self.stop_btn.configure(state="disabled")

    def _animate_btn(self):
        if not self._generating:
            return
        dots = "." * (self._anim_count % 4)
        self.generate_btn.configure(text=f"⏳ Generating{dots}")
        self._anim_count += 1
        self.after(500, self._animate_btn)

    def _generate_worker(self, key, code, instructor, section, school_year, semester):
        try:
            payload = generate_course_syllabus(
                key, course_code=code, instructor=instructor, section=section,
                school_year=school_year, semester=semester,
            )
            db_manager.upsert_syllabus(payload)
            self._gen_queue.put(("ok", code))
        except InterruptedError:
            self._gen_queue.put(("cancel", None))
        except Exception as e:
            self._gen_queue.put(("error", e))

    def _poll_generate_queue(self):
        try:
            status, result = self._gen_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_generate_queue)
            return

        self.progress.stop()
        self.generate_btn.configure(state="normal", text="⚙ Generate Syllabus")
        self.stop_btn.configure(state="disabled")
        self._generating = False

        if status == "ok":
            code = result
            self.current_course_code = code
            self._log(f"[OK] Validated & saved to database as '{code}'.")
            self.refresh_records()
            if self.records_tree.exists(code):
                self.records_tree.selection_set(code)
                self.records_tree.see(code)
            try:
                self._preview_in_browser(code)
            except Exception as e:
                self._log(f"[ERROR] Preview failed: {e}")
        elif status == "cancel":
            self._log("[WARNING] Generation cancelled by user.")
            messagebox.showinfo("Cancelled", "Syllabus generation was cancelled.")
        else:
            e = result
            self._log(f"[ERROR] {e}")
            messagebox.showerror("Generation failed", str(e))

    def _preview_in_browser(self, code: str):
        preview_path = os.path.join(OUT_DIR, f"_preview_{code.replace(' ', '_')}.html")
        export_engine.export_html(code, preview_path)
        self.last_export_path = preview_path
        
        if self.preview_lbl:
            self.preview_lbl.pack_forget()
        
        if self.preview_frame:
            self.preview_frame.destroy()
            
        self.preview_frame = tk.Frame(self.right_panel)
        self.preview_frame.pack(fill="both", expand=True)
        
        try:
            html_frame = HtmlFrame(self.preview_frame, messages_enabled=False)
            html_frame.load_file(preview_path)
            html_frame.pack(fill="both", expand=True)
            self._log(f"[OK] Preview updated for: {code}")
        except Exception as e:
            self._log(f"[ERROR] Could not load internal preview: {e}")
            messagebox.showerror("Preview Error", "Failed to load internal preview.")

    def _require_course(self) -> str:
        if not self.current_course_code:
            messagebox.showwarning("No syllabus yet", "Please click 'Generate Syllabus' first.")
            return None
        return self.current_course_code

    def _show_toast(self, title, message):
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#2d2d2d")
        
        lbl_title = tk.Label(toast, text=title, font=("Segoe UI", 10, "bold"), bg="#2d2d2d", fg="#D4AF37")
        lbl_title.pack(anchor="w", padx=15, pady=(10, 2))
        lbl_msg = tk.Label(toast, text=message, font=("Segoe UI", 9), bg="#2d2d2d", fg="#ffffff")
        lbl_msg.pack(anchor="w", padx=15, pady=(0, 10))
        
        self.update_idletasks()
        x = self.winfo_x() + self.winfo_width() - toast.winfo_reqwidth() - 20
        y = self.winfo_y() + 60
        toast.geometry(f"+{x}+{y}")
        self.after(3500, toast.destroy)

    def _run_export_thread(self, format_type, export_func, path):
        self._show_toast("Download Started", f"Exporting syllabus as {format_type}...\nPlease wait.")
        def worker():
            try:
                export_func()
                self.after(0, lambda: self._on_export_success(format_type, path))
            except Exception as e:
                self.after(0, lambda: self._on_export_error(format_type, e))
        threading.Thread(target=worker, daemon=True).start()
        
    def _on_export_success(self, format_type, path):
        self.last_export_path = path
        self._log(f"[OK] Exported {format_type} -> {path}")
        self._show_toast("Download Complete", f"Successfully saved {format_type}!")
        
    def _on_export_error(self, format_type, e):
        self._log(f"[ERROR] {format_type} export failed: {e}")
        self._show_toast("Download Failed", f"Error exporting {format_type}.")
        if isinstance(e, ImportError):
             messagebox.showerror("Missing dependency", str(e))
        else:
             messagebox.showerror(f"{format_type} export failed", str(e))

    def on_download_html(self):
        code = self._require_course()
        if not code: return
        default_name = f"{code.replace(' ', '_')}_Syllabus.html"
        path = filedialog.asksaveasfilename(defaultextension=".html", initialfile=default_name,
                                             filetypes=[("HTML file", "*.html")])
        if not path: return
        def run_export():
            export_engine.export_html(code, path)
        self._run_export_thread("HTML", run_export, path)

    def on_download_docx(self):
        code = self._require_course()
        if not code: return
        default_name = f"{code.replace(' ', '_')}_Syllabus.docx"
        path = filedialog.asksaveasfilename(defaultextension=".docx", initialfile=default_name,
                                             filetypes=[("Word Document", "*.docx")])
        if not path: return
        def run_export():
            try: export_engine.export_docx(code, path)
            except ImportError: raise ImportError("python-docx is not installed.\nInstall it with: pip install python-docx")
        self._run_export_thread("DOCX", run_export, path)

    def on_print(self):
        if not self.last_export_path or not os.path.exists(self.last_export_path):
            messagebox.showwarning("Nothing to print", "Generate or export a syllabus first.")
            return
        path = self.last_export_path
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(path, "print")
                self._log(f"[OK] Sent to default printer: {path}")
            elif system == "Darwin":
                subprocess.run(["lp", path], check=True)
                self._log(f"[OK] Sent to default printer via lp: {path}")
            else:
                subprocess.run(["lp", path], check=True)
                self._log(f"[OK] Sent to default printer via lp: {path}")
        except Exception as e:
            self._log(f"[WARNING] Could not print directly ({e}). Opening in browser for manual print (Ctrl+P).")
            webbrowser.open(f"file://{os.path.abspath(path)}")


if __name__ == "__main__":
    app = OBEApp()
    app.mainloop()