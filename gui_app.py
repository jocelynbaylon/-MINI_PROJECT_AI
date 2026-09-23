"""
gui_app.py
----------
Desktop front-end for the OBE Syllabus Generator microservice.

Course dropdown -> input fields (Instructor / Section / School Year / Semester)
-> [Generate Syllabus] (LLM engine -> Pydantic validation -> SQLite)
-> [Download HTML] / [Convert to PDF] / [Print]
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


class OBEApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI-Powered OBE Syllabus Generator - CCS")
        self.geometry("900x700")
        self.minsize(820, 600)
        self.configure(bg="#eef0f2")
        self.last_export_path = None
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
        logo_path = os.path.join(APP_DIR, "University_of_Perpetual_Help.png")
        if HAS_PIL and os.path.exists(logo_path):
            img = Image.open(logo_path).resize((44, 44))
            self._logo_img = ImageTk.PhotoImage(img)
            tk.Label(header, image=self._logo_img, bg="#7a0c1e").pack(side="left", padx=12)
        tk.Label(header, text="College of Computer Studies — OBE Syllabus Generator",
                 fg="white", bg="#7a0c1e", font=("Segoe UI", 14, "bold")).pack(side="left", pady=12)

    def _build_form(self):
        panel = tk.LabelFrame(self, text="Course & Class Details", padx=12, pady=12)
        panel.pack(fill="x", padx=14, pady=10)

        labels = ["Course", "Course Code", "Instructor", "Section", "School Year", "Semester"]
        for i, text in enumerate(labels):
            tk.Label(panel, text=text).grid(row=i // 3, column=(i % 3) * 2, sticky="w", padx=4, pady=4)

        self.course_var = tk.StringVar()
        self.course_map = {v["title"]: k for k, v in COURSES.items()}
        course_combo = ttk.Combobox(panel, textvariable=self.course_var, state="readonly",
                                     values=list(self.course_map.keys()), width=32)
        course_combo.current(0)
        course_combo.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        course_combo.bind("<<ComboboxSelected>>", self._on_course_change)

        self.code_var = tk.StringVar()
        tk.Entry(panel, textvariable=self.code_var, width=18).grid(row=0, column=3, padx=4, pady=4)

        self.instructor_var = tk.StringVar(value="(Instructor Name)")
        tk.Entry(panel, textvariable=self.instructor_var, width=22).grid(row=0, column=5, padx=4, pady=4)

        self.section_var = tk.StringVar(value="(Section)")
        tk.Entry(panel, textvariable=self.section_var, width=18).grid(row=1, column=1, padx=4, pady=4)

        self.sy_var = tk.StringVar(value="2026-2027")
        tk.Entry(panel, textvariable=self.sy_var, width=18).grid(row=1, column=3, padx=4, pady=4)

        self.sem_var = tk.StringVar(value="1st Semester")
        ttk.Combobox(panel, textvariable=self.sem_var, state="readonly",
                     values=["1st Semester", "2nd Semester"], width=16).grid(row=1, column=5, padx=4, pady=4)

        self._on_course_change()

    def _build_actions(self):
        bar = tk.Frame(self)
        bar.pack(fill="x", padx=14, pady=6)
        self.generate_btn = tk.Button(bar, text="⚙ Generate Syllabus", bg="#7a0c1e", fg="white",
                                       command=self.on_generate)
        self.generate_btn.pack(side="left", padx=4)
        tk.Button(bar, text="⬇ Download HTML", command=self.on_download_html).pack(side="left", padx=4)
        tk.Button(bar, text="🖨 Print", command=self.on_print).pack(side="left", padx=4)
        tk.Button(bar, text="📄 Convert to PDF", bg="#8a6d00", fg="white",
                  command=self.on_convert_pdf).pack(side="left", padx=4)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=130)
        self.progress.pack(side="left", padx=12)

    def _build_records(self):
        frame = tk.LabelFrame(self, text="Saved Syllabuses")
        frame.pack(fill="both", expand=True, padx=14, pady=(10, 4))

        table_area = tk.Frame(frame)
        table_area.pack(fill="both", expand=True, padx=6, pady=6)

        columns = ("code", "title", "instructor", "section", "sy", "sem", "saved")
        headings = {
            "code": ("Course Code", 90),
            "title": ("Course Title", 220),
            "instructor": ("Instructor", 120),
            "section": ("Section", 80),
            "sy": ("School Year", 90),
            "sem": ("Semester", 100),
            "saved": ("Date Saved", 140),
        }
        self.records_tree = ttk.Treeview(table_area, columns=columns, show="headings",
                                          height=7, selectmode="browse")
        for col, (text, width) in headings.items():
            self.records_tree.heading(col, text=text)
            self.records_tree.column(col, width=width, anchor="w")

        vsb = ttk.Scrollbar(table_area, orient="vertical", command=self.records_tree.yview)
        self.records_tree.configure(yscrollcommand=vsb.set)
        self.records_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self.records_tree.bind("<Double-1>", lambda e: self.on_preview_selected())
        self.records_tree.bind("<<TreeviewSelect>>", self._on_record_select)

        btns = tk.Frame(frame)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        tk.Button(btns, text="🔍 Preview Selected", command=self.on_preview_selected).pack(side="left", padx=4)
        tk.Button(btns, text="🔄 Refresh List", command=self.refresh_records).pack(side="left", padx=4)
        tk.Button(btns, text="🗑 Delete Selected", command=self.on_delete_selected).pack(side="left", padx=4)

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
        code = sel[0]
        if not messagebox.askyesno("Confirm delete", f"Delete the saved syllabus '{code}'?\nThis cannot be undone."):
            return
        try:
            db_manager.delete_course(code)
            if self.current_course_code == code:
                self.current_course_code = None
            self._log(f"[OK] Deleted '{code}' from database.")
            self.refresh_records()
        except Exception as e:
            self._log(f"[ERROR] Could not delete '{code}': {e}")

    def _build_log(self):
        frame = tk.LabelFrame(self, text="Activity Log")
        frame.pack(fill="x", padx=14, pady=(4, 10))
        self.log_text = tk.Text(frame, state="disabled", wrap="word", bg="#111", fg="#0f0",
                                 font=("Consolas", 9), height=6)
        self.log_text.pack(fill="both", expand=True)

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
        self.generate_btn.configure(state="disabled", text="⏳ Generating...")
        self.progress.start(12)
        self._log(f"Generating syllabus for {code} ({COURSES[key]['title']})...")

        # The Ollama call (and any DB write) runs on a background thread so the
        # window stays responsive instead of freezing for the whole request;
        # the main thread just polls a queue for the result.
        threading.Thread(
            target=self._generate_worker,
            args=(key, code, instructor, section, school_year, semester),
            daemon=True,
        ).start()
        self.after(100, self._poll_generate_queue)

    def _generate_worker(self, key, code, instructor, section, school_year, semester):
        try:
            payload = generate_course_syllabus(
                key, course_code=code, instructor=instructor, section=section,
                school_year=school_year, semester=semester,
            )
            db_manager.upsert_syllabus(payload)
            self._gen_queue.put(("ok", code))
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
        else:
            e = result
            self._log(f"[ERROR] {e}")
            messagebox.showerror("Generation failed", str(e))

    def _preview_in_browser(self, code: str):
        preview_path = os.path.join(OUT_DIR, f"_preview_{code.replace(' ', '_')}.html")
        export_engine.export_html(code, preview_path)
        self.last_export_path = preview_path
        
        # Create a new window inside the app for the preview
        preview_win = tk.Toplevel(self)
        preview_win.title(f"Syllabus Preview - {code}")
        preview_win.geometry("900x700")
        
        try:
            html_frame = HtmlFrame(preview_win, messages_enabled=False)
            html_frame.load_file(preview_path)
            html_frame.pack(fill="both", expand=True)
            self._log(f"[OK] Preview opened inside the application: {code}")
        except Exception as e:
            self._log(f"[ERROR] Could not load internal preview: {e}")
            messagebox.showerror("Preview Error", "Failed to load internal preview.")

    def _require_course(self) -> str:
        if not self.current_course_code:
            messagebox.showwarning("No syllabus yet", "Please click 'Generate Syllabus' first.")
            return None
        return self.current_course_code

    def on_download_html(self):
        code = self._require_course()
        if not code:
            return
        default_name = f"{code.replace(' ', '_')}_Syllabus.html"
        path = filedialog.asksaveasfilename(defaultextension=".html", initialfile=default_name,
                                             filetypes=[("HTML file", "*.html")])
        if not path:
            return
        export_engine.export_html(code, path)
        self.last_export_path = path
        self._log(f"[OK] Saved HTML syllabus -> {path}")

    def on_convert_pdf(self):
        code = self._require_course()
        if not code:
            return
        default_name = f"{code.replace(' ', '_')}_Syllabus.pdf"
        path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=default_name,
                                             filetypes=[("PDF file", "*.pdf")])
        if not path:
            return
        try:
            export_engine.export_pdf(code, path)
            self.last_export_path = path
            self._log(f"[OK] Exported PDF -> {path}")
        except ImportError:
            self._log("[ERROR] xhtml2pdf is not installed. Run: pip install xhtml2pdf")
            messagebox.showerror("Missing dependency", "Install it with:\n\npip install xhtml2pdf")
        except Exception as e:
            self._log(f"[ERROR] PDF export failed: {e}")
            messagebox.showerror("PDF export failed", str(e))

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