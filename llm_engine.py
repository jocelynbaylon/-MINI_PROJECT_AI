"""
llm_engine.py
-------------
Wraps the local Ollama REST API (format="json") so Qwen2.5 returns
schema-constrained output. On ValidationError or JSONDecodeError it
re-prompts automatically (max 3 attempts). If Ollama is not reachable,
it transparently falls back to the deterministic offline generator in
mock_data.py so the rest of the pipeline (DB + export) still works.
"""

import json
import os
import sys
import requests
from pydantic import ValidationError

from obe_schemas import OBESyllabusPayload
from mock_data import generate_mock_payload, COURSES

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
MAX_RETRIES = 3

# How long Ollama should keep the model loaded in memory after a request.
# Without this, Ollama's default is to unload the model ~5 minutes after each
# call, so the *next* generate has to pay the full load-into-RAM/VRAM cost
# all over again on top of actual inference time. Keeping it warm removes
# that reload cost for every generate after the first one in a session.
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")

# Reused across every request instead of opening a fresh TCP/HTTP connection
# each time -- cuts noticeable latency off retries and the reachability ping.
_SESSION = requests.Session()

SYSTEM_PROMPT = """You are an OBE (Outcome-Based Education) curriculum design assistant for a
College of Computer Studies. You MUST return ONLY valid JSON matching the exact schema you
are given -- no markdown fences, no commentary. Use active Bloom's Taxonomy verbs
(never "understand", "know", "learn", "study"). Every weekly Knowledge/Skills/Attitude outcome
must be a full sentence starting with an action verb.

Example of expected valid JSON structure (do not copy the content, just the format):
{
  "course_code": "...",
  "course_title": "...",
  "instructor": "...",
  "section": "...",
  "school_year": "...",
  "semester": "...",
  "course_outcomes": [
    {"clo_number": 1, "bloom_level": "Apply/Analyze", "co_description": "Analyze requirements...", "mapped_po": [1, 2]}
  ],
  "grading_breakdown": {
    "quizzes_pct": 30.0, "research_pct": 20.0, "seatwork_lab_pct": 50.0,
    "class_standing_weight": 70.0, "major_exam_weight": 30.0
  },
  "weekly_schedule": [
    {
      "week_number": 1,
      "period": "PRELIM",
      "topics": ["Intro"],
      "llos": [
        {"category": "K", "outcome_text": "Identify the basic concepts."},
        {"category": "S", "outcome_text": "Demonstrate the initial setup."},
        {"category": "A", "outcome_text": "Value the importance of the topic."}
      ],
      "teaching_learning_activity": "Lecture",
      "assessment_tool": "Quiz",
      "evidence": "Output",
      "aligned_co": [1]
    }
  ]
}
"""


def _ollama_reachable() -> bool:
    force = os.environ.get("OBE_FORCE_MOCK")
    if force is not None:
        return force == "0"
    try:
        _SESSION.get(f"{OLLAMA_HOST}/api/tags", timeout=0.8)
        return True
    except requests.exceptions.RequestException:
        return False


_mock_mode_cache = {"value": None}
CANCEL_FLAG = False

def cancel_generation():
    global CANCEL_FLAG
    CANCEL_FLAG = True

def is_mock_mode(force_refresh: bool = False) -> bool:
    """Lazily checks (and caches) whether the local Ollama server is reachable.

    This used to run once, synchronously, at import time -- which meant the
    whole app (window included) waited on a network call before it could even
    appear. Now the check only happens the first time it's actually needed
    (and callers can run it off the main thread), and the result is cached so
    every later generate call skips the ping entirely.
    """
    if force_refresh or _mock_mode_cache["value"] is None:
        _mock_mode_cache["value"] = not _ollama_reachable()
    return _mock_mode_cache["value"]


def _call_ollama(user_prompt: str) -> str:
    global CANCEL_FLAG
    CANCEL_FLAG = False
    
    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": user_prompt,
        "format": "json",
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_ctx": 1500,
            "num_predict": 1024,
            "num_thread": 8
        },
        "keep_alive": OLLAMA_KEEP_ALIVE,
    }
    resp = _SESSION.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=600, stream=True)
    resp.raise_for_status()
    
    full_response = []
    for line in resp.iter_lines():
        if CANCEL_FLAG:
            raise InterruptedError("Generation cancelled by user.")
        if line:
            chunk = json.loads(line)
            full_response.append(chunk.get("response", ""))
            
    return "".join(full_response)


def warm_up_model():
    """Fires a minimal request so the model is already loaded into memory
    (and stays loaded, per OLLAMA_KEEP_ALIVE) before the user's first real
    'Generate Syllabus' click. Safe to call from a background thread; any
    failure is silently ignored since generation will just load it on
    demand instead."""
    if is_mock_mode():
        return
    try:
        _SESSION.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": MODEL_NAME, "prompt": "", "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE},
            timeout=600,
        )
    except requests.exceptions.RequestException:
        pass


def _build_prompt(course_title: str, course_code: str, instructor: str,
                   section: str, school_year: str, semester: str) -> str:
    return f"""Generate a complete OBE syllabus JSON object for the course
"{course_title}" (code: {course_code}) taught by {instructor}, section {section},
{semester} SY {school_year}.

Return a single JSON object with EXACTLY these top-level keys:
course_code, course_title, instructor, section, school_year, semester,
course_outcomes (4-6 items: clo_number, bloom_level ["Remember/Understand"|"Apply/Analyze"|"Evaluate/Create"],
co_description, mapped_po [ints 1-6]),
grading_breakdown (quizzes_pct, research_pct, seatwork_lab_pct summing to 100;
class_standing_weight + major_exam_weight summing to 100),
weekly_schedule (EXACTLY 18 items; week_number 1-18; period "PRELIM"|"MIDTERM"|"FINAL";
week 6 = Prelim Exam, week 12 = Midterm Exam, week 18 = Final Exam;
topics [list]; llos [>=3 items: category "K"|"S"|"A", outcome_text]; teaching_learning_activity;
assessment_tool; evidence; aligned_co [clo_number ints -- every declared CLO must be
referenced at least once across the whole schedule])."""


def generate_validated(prompt: str, mock_fn) -> OBESyllabusPayload:
    """Generic retry-and-validate loop shared by every generation call."""
    if is_mock_mode():
        return OBESyllabusPayload.model_validate(mock_fn())

    last_error = None
    live_prompt = prompt
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = _call_ollama(live_prompt)
        except InterruptedError as e:
            raise e
        except requests.exceptions.RequestException as e:
            last_error = f"Ollama HTTP error: {e}"
            print(f"[WARNING] attempt {attempt}/{MAX_RETRIES}: {e}", file=sys.stderr)
            if attempt == MAX_RETRIES:
                print("[INFO] falling back to offline mock generator.", file=sys.stderr)
                return OBESyllabusPayload.model_validate(mock_fn())
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON syntax: {e}"
            live_prompt = f"{prompt}\n\nYour previous output was not valid JSON ({last_error}). Return ONLY valid JSON."
            continue

        try:
            return OBESyllabusPayload.model_validate(data)
        except ValidationError as e:
            last_error = e.errors()
            live_prompt = (f"{prompt}\n\nYour previous output failed schema validation: {last_error}. "
                            "Fix every field and resubmit ONLY the corrected JSON.")

    print("[WARNING] exceeded retry limit; falling back to offline mock generator.", file=sys.stderr)
    return OBESyllabusPayload.model_validate(mock_fn())


def generate_course_syllabus(course_key: str, course_code: str = None, instructor: str = "(Instructor Name)",
                              section: str = "(Section)", school_year: str = "2026-2027",
                              semester: str = "1st Semester") -> OBESyllabusPayload:
    """Public entry point used by the GUI. course_key is one of mock_data.COURSES keys."""
    src = COURSES[course_key]
    code = course_code or src["default_code"]
    mock_fn = lambda: generate_mock_payload(course_key, code, instructor, section, school_year, semester)
    prompt = _build_prompt(src["title"], code, instructor, section, school_year, semester)
    return generate_validated(prompt, mock_fn)