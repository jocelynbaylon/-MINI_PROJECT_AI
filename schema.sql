PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS courses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code     TEXT NOT NULL UNIQUE,
    course_title    TEXT NOT NULL,
    instructor      TEXT,
    section         TEXT,
    school_year     TEXT,
    semester        TEXT,
    quizzes_pct     REAL DEFAULT 30.0,
    research_pct    REAL DEFAULT 20.0,
    seatwork_lab_pct REAL DEFAULT 50.0,
    class_standing_weight REAL DEFAULT 70.0,
    major_exam_weight REAL DEFAULT 30.0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS course_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    clo_number      INTEGER NOT NULL,
    bloom_level     TEXT NOT NULL,
    co_description  TEXT NOT NULL,
    mapped_po       TEXT NOT NULL,   -- comma-separated PLO ints
    UNIQUE(course_id, clo_number)
);

CREATE TABLE IF NOT EXISTS weekly_schedules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    week_number     INTEGER NOT NULL,
    period          TEXT NOT NULL,
    topics          TEXT NOT NULL,   -- pipe-separated
    teaching_learning_activity TEXT,
    assessment_tool TEXT,
    evidence        TEXT,
    aligned_co      TEXT NOT NULL,   -- comma-separated clo_number ints
    UNIQUE(course_id, week_number)
);

CREATE TABLE IF NOT EXISTS lesson_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id         INTEGER NOT NULL REFERENCES weekly_schedules(id) ON DELETE CASCADE,
    category        TEXT NOT NULL CHECK (category IN ('K','S','A')),
    outcome_text    TEXT NOT NULL
);
