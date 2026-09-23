"""
export_engine.py
-----------------
Queries SQLite by course_code (via db_manager) and compiles the record into
the official CCS syllabus layout using Jinja2, producing a browser-ready
HTML file. export_pdf() converts that HTML to PDF with xhtml2pdf (pure
Python -- no external wkhtmltopdf binary required).
"""

import os
import base64
from jinja2 import Environment, FileSystemLoader

import db_manager

BASE_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
LOGO_PATH = os.path.join(BASE_DIR, "University_of_Perpetual_Help.png")

# Built once at import time and reused for every render: recreating the Jinja
# Environment (which re-reads and re-parses the template file) on every single
# export/preview call was pure overhead, since the template never changes at
# runtime.
_ENV = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
_TEMPLATE = _ENV.get_template("uphsd_ccs_template.html")

# The logo PNG is likewise constant, so read + base64-encode it once instead
# of hitting disk again on every export (including the auto-preview that
# fires after every "Generate Syllabus" click).
_logo_cache = {"value": None}


def _logo_b64() -> str:
    if _logo_cache["value"] is None:
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, "rb") as f:
                _logo_cache["value"] = base64.b64encode(f.read()).decode()
        else:
            _logo_cache["value"] = ""
    return _logo_cache["value"]


def render_html(course_code: str) -> str:
    """Returns the rendered syllabus as an HTML string."""
    data = db_manager.get_syllabus(course_code)
    return _TEMPLATE.render(
        course=data["course"],
        course_outcomes=data["course_outcomes"],
        weekly_schedule=data["weekly_schedule"],
        logo_b64=_logo_b64(),
    )


def export_html(course_code: str, out_path: str) -> str:
    html = render_html(course_code)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def export_pdf(course_code: str, out_path: str) -> str:
    """Converts the rendered syllabus HTML into a PDF file using xhtml2pdf."""
    from xhtml2pdf import pisa  # imported lazily so the HTML-only path never needs it
    html = render_html(course_code)
    with open(out_path, "wb") as f:
        result = pisa.CreatePDF(src=html, dest=f)
    if result.err:
        raise RuntimeError(f"xhtml2pdf reported {result.err} error(s) while rendering {course_code}.")
    return out_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python export_engine.py <COURSE_CODE> [html|pdf]")
        sys.exit(1)
    code = sys.argv[1]
    fmt = sys.argv[2] if len(sys.argv) > 2 else "html"
    out = f"{code.replace(' ', '_')}_Syllabus.{fmt}"
    if fmt == "pdf":
        export_pdf(code, out)
    else:
        export_html(code, out)
    print(f"Exported -> {out}")
