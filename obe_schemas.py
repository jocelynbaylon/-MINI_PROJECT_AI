"""
obe_schemas.py
--------------
Pydantic data models (the "data contract") that every JSON payload produced
by the LLM engine must satisfy before it is allowed to touch the database.
If Ollama/Qwen returns malformed or non-OBE-compliant JSON, ValidationError
is raised here and the caller (llm_engine.py) auto re-prompts the model.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Literal

BLOOM_LEVELS = Literal[
    "Remember/Understand",
    "Apply/Analyze",
    "Evaluate/Create",
]

NON_MEASURABLE_VERBS = {
    "understand", "learn", "know", "be exposed to", "study", "be familiar with"
}


class CourseOutcomeItem(BaseModel):
    clo_number: int = Field(..., ge=1)
    bloom_level: BLOOM_LEVELS
    co_description: str = Field(..., min_length=10)
    mapped_po: List[int] = Field(..., min_length=1)

    @field_validator("co_description")
    @classmethod
    def reject_non_measurable_language(cls, v: str) -> str:
        lowered = v.lower()
        for verb in NON_MEASURABLE_VERBS:
            if lowered.startswith(verb) or f" {verb} " in lowered:
                raise ValueError(
                    f"co_description uses a non-measurable verb ('{verb}')."
                )
        return v

    @field_validator("mapped_po")
    @classmethod
    def po_within_range(cls, v: List[int]) -> List[int]:
        for po in v:
            if not (1 <= po <= 6):
                raise ValueError(f"mapped_po value {po} is outside PLO 1-6 range.")
        return v


class CourseOutcomeBatch(BaseModel):
    course_title: str
    course_outcomes: List[CourseOutcomeItem] = Field(..., min_length=4, max_length=6)


class GradingBreakdown(BaseModel):
    quizzes_pct: float = Field(30.0, ge=0, le=100)
    research_pct: float = Field(20.0, ge=0, le=100)
    seatwork_lab_pct: float = Field(50.0, ge=0, le=100)
    class_standing_weight: float = Field(70.0, ge=0, le=100)
    major_exam_weight: float = Field(30.0, ge=0, le=100)

    @field_validator("seatwork_lab_pct")
    @classmethod
    def class_standing_components_sum_to_100(cls, v, info):
        total = info.data.get("quizzes_pct", 0) + info.data.get("research_pct", 0) + v
        if round(total, 2) != 100.0:
            raise ValueError(f"Class Standing components must total 100% (got {total}%).")
        return v

    @field_validator("major_exam_weight")
    @classmethod
    def term_grade_components_sum_to_100(cls, v, info):
        total = info.data.get("class_standing_weight", 0) + v
        if round(total, 2) != 100.0:
            raise ValueError(f"Term Grade components must total 100% (got {total}%).")
        return v


class LessonLearningOutcome(BaseModel):
    category: Literal["K", "S", "A"]
    outcome_text: str = Field(..., min_length=5)


class WeeklySchedule(BaseModel):
    week_number: int = Field(..., ge=1, le=18)
    period: Literal["PRELIM", "MIDTERM", "FINAL"]
    topics: List[str] = Field(..., min_length=1)
    llos: List[LessonLearningOutcome] = Field(..., min_length=3)
    teaching_learning_activity: str
    assessment_tool: str
    evidence: str
    aligned_co: List[int] = Field(..., min_length=1)


class OBESyllabusPayload(BaseModel):
    course_code: str
    course_title: str
    instructor: str = "(Instructor Name)"
    section: str = "(Section)"
    school_year: str = "2026-2027"
    semester: str = "1st Semester"
    course_outcomes: List[CourseOutcomeItem]
    grading_breakdown: GradingBreakdown
    weekly_schedule: List[WeeklySchedule]

    @field_validator("weekly_schedule")
    @classmethod
    def every_co_is_referenced_at_least_once(cls, v, info):
        cos = info.data.get("course_outcomes")
        if not cos:
            return v
        declared = {co.clo_number for co in cos}
        referenced = {n for week in v for n in week.aligned_co}
        missing = declared - referenced
        if missing:
            raise ValueError(f"CLO(s) {sorted(missing)} are never referenced in weekly_schedule.")
        return v
