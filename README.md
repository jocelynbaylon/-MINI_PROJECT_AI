# AI-Powered OBE Syllabus Generator (Full Python Version)

A desktop microservice for the College of Computer Studies that generates
Outcome-Based Education (OBE) syllabi for 5 subjects:

- Computer Graphics Programming
- Database Systems 1
- Data Mining
- Software Engineering
- Information Assurance and Security

## Architecture (matches the mini-project brief)

| File | Role |
|---|---|
| `obe_schemas.py` | Pydantic data contracts (CLOs, grading, 18-week schedule, K/S/A). |
| `mock_data.py` | Source topics/CLOs for the 5 subjects + offline (no-Ollama) generator. |
| `llm_engine.py` | Ollama/Qwen JSON-mode wrapper with a 3-attempt validation retry loop; falls back to the offline generator if Ollama isn't running. |
| `schema.sql` | Normalized SQLite DDL (`courses`, `course_outcomes`, `weekly_schedules`, `lesson_outcomes`) with foreign keys + cascading deletes. |
| `db_manager.py` | DB init, ingestion, CRUD (e.g. edit a CLO before export), read-back for rendering. |
| `templates/uphsd_ccs_template.html` | Jinja2 template for the official CCS syllabus layout. |
| `export_engine.py` | Compiles a DB record into browser-ready HTML, and into PDF via `xhtml2pdf`. |
| `gui_app.py` | Tkinter desktop app: course picker, class-detail fields, and **Generate / Download HTML / Print / Convert to PDF** buttons. |

## Setup

```bash
pip install -r requirements.txt

# Optional, for real LLM generation instead of the offline generator:
ollama pull qwen2.5
ollama serve
```

## Run

```bash
python gui_app.py
```

1. Pick a course from the dropdown (auto-fills a default course code).
2. Fill in Instructor / Section / School Year / Semester.
3. Click **Generate Syllabus** — this calls the LLM engine (or the offline
   generator if Ollama isn't reachable), validates the JSON against the
   Pydantic schema, saves it to `obe_syllabus.db`, and opens a live preview
   in your browser.
4. **Download HTML** / **Convert to PDF** save the compiled syllabus wherever
   you choose. **Print** sends the last exported file straight to your
   default printer (falls back to opening it in the browser for Ctrl+P if
   direct printing isn't available on your OS).

## Notes

- Without a local Ollama server, the app runs fully offline using a
  deterministic generator in `mock_data.py` that still produces
  schema-valid, Bloom's-aligned content for all 5 subjects — so the whole
  pipeline (validation -> DB -> export) is testable without any AI setup.
- Force offline mode explicitly with `OBE_FORCE_MOCK=1 python gui_app.py`,
  or force live mode with `OBE_FORCE_MOCK=0`.
- Each course's Prelim/Midterm/Final exam weeks are auto-placed at weeks
  6, 12, and 18 of the 18-week schedule.
