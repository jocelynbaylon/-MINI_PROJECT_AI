"""
db_manager.py
-------------
Handles database initialization, structured JSON ingestion (from a
validated OBESyllabusPayload), and CRUD operations against
obe_syllabus.db (SQLite, foreign keys + cascading deletes).
"""

import sqlite3
import os
from obe_schemas import OBESyllabusPayload

DB_PATH = os.path.join(os.path.dirname(__file__), "obe_syllabus.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        ddl = f.read()
    conn = get_connection()
    try:
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()


def upsert_syllabus(payload: OBESyllabusPayload) -> int:
    """Ingests a validated payload using batch inserts for better performance. 
    Replaces any prior data for the same course_code."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM courses WHERE course_code = ?", (payload.course_code,))
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM courses WHERE id = ?", (row["id"],))  # cascades

        gb = payload.grading_breakdown
        cur.execute(
            """INSERT INTO courses (course_code, course_title, instructor, section,
               school_year, semester, quizzes_pct, research_pct, seatwork_lab_pct,
               class_standing_weight, major_exam_weight)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (payload.course_code, payload.course_title, payload.instructor, payload.section,
             payload.school_year, payload.semester, gb.quizzes_pct, gb.research_pct,
             gb.seatwork_lab_pct, gb.class_standing_weight, gb.major_exam_weight),
        )
        course_id = cur.lastrowid

        # Batch insert for Course Outcomes
        co_data = [
            (course_id, co.clo_number, co.bloom_level, co.co_description, ",".join(str(p) for p in co.mapped_po))
            for co in payload.course_outcomes
        ]
        cur.executemany(
            """INSERT INTO course_outcomes (course_id, clo_number, bloom_level,
               co_description, mapped_po) VALUES (?,?,?,?,?)""",
            co_data
        )

        llo_data = []
        for wk in payload.weekly_schedule:
            cur.execute(
                """INSERT INTO weekly_schedules (course_id, week_number, period, topics,
                   teaching_learning_activity, assessment_tool, evidence, aligned_co)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (course_id, wk.week_number, wk.period, " | ".join(wk.topics),
                 wk.teaching_learning_activity, wk.assessment_tool, wk.evidence,
                 ",".join(str(c) for c in wk.aligned_co)),
            )
            week_id = cur.lastrowid
            
            # Prepare lesson outcomes for a single batch insert later
            for llo in wk.llos:
                llo_data.append((week_id, llo.category, llo.outcome_text))

        # Batch insert for all Lesson Outcomes
        if llo_data:
            cur.executemany(
                "INSERT INTO lesson_outcomes (week_id, category, outcome_text) VALUES (?,?,?)",
                llo_data
            )

        conn.commit()
        return course_id
    finally:
        conn.close()


def get_syllabus(course_code: str) -> dict:
    """Reads a full syllabus back out of the DB for export_engine.py with optimized queries."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM courses WHERE course_code = ?", (course_code,))
        course = cur.fetchone()
        if not course:
            raise LookupError(f"No syllabus found for course_code={course_code!r}")

        cur.execute("SELECT * FROM course_outcomes WHERE course_id = ? ORDER BY clo_number",
                    (course["id"],))
        clos = [dict(r) for r in cur.fetchall()]

        # Fetch all weekly schedules
        cur.execute("SELECT * FROM weekly_schedules WHERE course_id = ? ORDER BY week_number",
                    (course["id"],))
        weeks = [dict(w) for w in cur.fetchall()]

        if weeks:
            week_ids = [w["id"] for w in weeks]
            placeholders = ",".join("?" * len(week_ids))
            
            # Fetch all lesson outcomes for these weeks in one query
            cur.execute(
                f"SELECT week_id, category, outcome_text FROM lesson_outcomes WHERE week_id IN ({placeholders})", 
                week_ids
            )
            all_llos = cur.fetchall()

            # Group LLOs by week_id
            llo_map = {w_id: [] for w_id in week_ids}
            for row in all_llos:
                llo_map[row["week_id"]].append({"category": row["category"], "outcome_text": row["outcome_text"]})

            # Reconstruct the weekly schedule structure
            for wd in weeks:
                wd["llos"] = llo_map.get(wd["id"], [])
                wd["topics"] = wd["topics"].split(" | ")
                wd["aligned_co"] = [int(x) for x in wd["aligned_co"].split(",") if x]

        return {"course": dict(course), "course_outcomes": clos, "weekly_schedule": weeks}
    finally:
        conn.close()


def list_courses() -> list:
    """Returns every saved syllabus with the fields needed for a summary list view,
    most recently generated first."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT course_code, course_title, instructor, section,
               school_year, semester, created_at
               FROM courses ORDER BY created_at DESC, course_title"""
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_outcome_text(course_code: str, clo_number: int, new_text: str):
    """Faculty edit interface: modify one CLO's description before export."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM courses WHERE course_code = ?", (course_code,))
        row = cur.fetchone()
        if not row:
            raise LookupError(f"No course_code={course_code!r}")
        cur.execute(
            "UPDATE course_outcomes SET co_description = ? WHERE course_id = ? AND clo_number = ?",
            (new_text, row["id"], clo_number),
        )
        conn.commit()
    finally:
        conn.close()


def delete_course(course_code: str):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM courses WHERE course_code = ?", (course_code,))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")