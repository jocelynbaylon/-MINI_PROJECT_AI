"""
mock_data.py
------------
Source data for the 5 CCS subjects plus a deterministic "offline generator"
that builds a schema-valid OBESyllabusPayload dict without calling an LLM.
llm_engine.py uses this as MOCK_MODE fallback, and it also doubles as the
`mock_fn` passed into the retry loop when Ollama is unreachable.
"""

COURSES = {
    "cgp": {
        "title": "Computer Graphics Programming",
        "default_code": "CGP 101",
        "clos": [
            ("Apply/Analyze", "Configure the OpenGL rendering environment and IDE toolchain required for graphics programming.", [2]),
            ("Apply/Analyze", "Implement 2D and 3D geometric transformations, including translation, rotation, and scaling.", [2, 3]),
            ("Apply/Analyze", "Apply projection, shading, and illumination techniques to render realistic 3D scenes.", [3]),
            ("Evaluate/Create", "Design an interactive, event-driven graphics application as a collaborative final project.", [3, 5]),
            ("Evaluate/Create", "Defend design decisions in a rendering pipeline through a documented technical report.", [5]),
        ],
        "weeks": [
            "Course Orientation & Graphics Pipeline Overview", "Development Environment Setup & Basic Windowing",
            "2D Primitives & Drawing Algorithms", "2D Geometric Transformations", "3D Coordinate Systems & Transformations",
            "Prelim Examination", "Viewing & Projection Techniques", "Clipping Algorithms",
            "Shading Models (Flat, Gouraud, Phong)", "Illumination & Lighting Models", "Texture Mapping",
            "Midterm Examination", "Rendering Pipeline & Rasterization", "Curves & Surfaces (Bezier/B-splines)",
            "Animation Principles & Keyframing", "Event-Driven Interactive Graphics Applications",
            "Final Project Development & Integration", "Final Examination / Project Defense",
        ],
    },
    "db1": {
        "title": "Database Systems 1",
        "default_code": "DB1 101",
        "clos": [
            ("Remember/Understand", "Explain the fundamental architecture and components of relational database management systems.", [1]),
            ("Apply/Analyze", "Design normalized relational database schemas using ER modeling and normalization techniques.", [2, 3]),
            ("Apply/Analyze", "Construct SQL queries involving joins, subqueries, and views to retrieve and manipulate data.", [2]),
            ("Apply/Analyze", "Implement transactions, constraints, and stored procedures to enforce data integrity.", [2, 3]),
            ("Evaluate/Create", "Design and deploy a functional database system as a capstone project for a real-world scenario.", [3, 5]),
        ],
        "weeks": [
            "Introduction to Database Systems & DBMS Architecture", "Entity-Relationship Modeling",
            "Relational Model & Relational Algebra", "Normalization (1NF-3NF, BCNF)", "SQL Fundamentals: DDL & DML",
            "Prelim Examination", "Advanced SQL: Joins, Subqueries, Views", "Constraints, Indexes & Transactions",
            "Stored Procedures & Triggers", "Database Design Case Study", "Concurrency Control & Locking",
            "Midterm Examination", "Database Security & Access Control", "Backup & Recovery Techniques",
            "Distributed Databases Overview", "NoSQL & Modern Database Paradigms",
            "Capstone Database Project Development", "Final Examination / Project Presentation",
        ],
    },
    "dm": {
        "title": "Data Mining",
        "default_code": "DM 101",
        "clos": [
            ("Remember/Understand", "Describe the knowledge discovery process and core concepts of data mining.", [1]),
            ("Apply/Analyze", "Apply data preprocessing techniques to prepare raw datasets for mining tasks.", [2]),
            ("Apply/Analyze", "Implement classification and clustering algorithms to extract patterns from data.", [2, 3]),
            ("Apply/Analyze", "Evaluate the performance of data mining models using appropriate validation metrics.", [3]),
            ("Evaluate/Create", "Design a complete data mining pipeline to solve a real-world analytical problem.", [3, 5]),
        ],
        "weeks": [
            "Introduction to Data Mining & KDD Process", "Data Preprocessing & Cleaning",
            "Data Warehousing & OLAP Concepts", "Association Rule Mining (Apriori Algorithm)", "Classification: Decision Trees",
            "Prelim Examination", "Classification: Naive Bayes & k-NN", "Clustering: K-Means Algorithm",
            "Hierarchical & Density-Based Clustering", "Regression Analysis Techniques", "Model Evaluation & Validation Metrics",
            "Midterm Examination", "Text Mining & Sentiment Analysis", "Web Mining Fundamentals",
            "Anomaly & Outlier Detection", "Big Data Mining Tools & Frameworks",
            "Data Mining Capstone Project", "Final Examination / Project Presentation",
        ],
    },
    "se": {
        "title": "Software Engineering",
        "default_code": "SE 101",
        "clos": [
            ("Remember/Understand", "Explain the phases of the software development life cycle and common process models.", [1]),
            ("Apply/Analyze", "Analyze and document software requirements using structured specification techniques.", [2]),
            ("Apply/Analyze", "Model software systems using UML diagrams for design and architecture representation.", [2, 3]),
            ("Apply/Analyze", "Apply software testing and quality assurance techniques to validate software correctness.", [2, 3]),
            ("Evaluate/Create", "Design and manage a collaborative software project applying Agile development practices.", [3, 5]),
        ],
        "weeks": [
            "Introduction to Software Engineering & SDLC Models", "Requirements Elicitation & Analysis",
            "Software Requirements Specification (SRS)", "System Design & Architecture Principles", "UML Modeling: Use Case & Class Diagrams",
            "Prelim Examination", "UML Modeling: Sequence & Activity Diagrams", "Software Design Patterns",
            "Agile & Scrum Methodologies", "Software Construction Best Practices", "Software Testing Fundamentals",
            "Midterm Examination", "Software Quality Assurance & Metrics", "Software Maintenance & Refactoring",
            "Project Management for Software Teams", "DevOps & CI/CD Concepts",
            "Capstone Software Project Development", "Final Examination / Project Presentation",
        ],
    },
    "ias": {
        "title": "Information Assurance and Security",
        "default_code": "IAS 101",
        "clos": [
            ("Remember/Understand", "Explain core information security concepts including the CIA triad and threat landscape.", [1]),
            ("Apply/Analyze", "Apply cryptographic techniques to secure data confidentiality and integrity.", [2]),
            ("Apply/Analyze", "Implement access control and authentication mechanisms to protect information systems.", [2, 3]),
            ("Apply/Analyze", "Analyze security incidents using digital forensics and risk assessment methods.", [3]),
            ("Evaluate/Create", "Design a comprehensive information security plan for an organizational scenario.", [3, 5]),
        ],
        "weeks": [
            "Introduction to Information Assurance & Security Concepts", "CIA Triad & Security Principles",
            "Cryptography Fundamentals", "Symmetric & Asymmetric Encryption", "Network Security Fundamentals",
            "Prelim Examination", "Access Control & Authentication Mechanisms", "Security Policies & Risk Management",
            "Malware Analysis & Threat Types", "Web Application Security", "Ethical Hacking & Penetration Testing Basics",
            "Midterm Examination", "Incident Response & Digital Forensics", "Security Auditing & Compliance Standards",
            "Cloud Security Fundamentals", "Security Awareness & Social Engineering",
            "Security Capstone Project", "Final Examination / Project Presentation",
        ],
    },
}

KV = {"prelim": ["Identify", "Define", "Describe", "Explain"],
      "midterm": ["Explain", "Analyze", "Describe"],
      "final": ["Analyze", "Evaluate", "Synthesize"]}
SV = {"prelim": ["Demonstrate", "Configure", "Construct"],
      "midterm": ["Implement", "Apply", "Develop"],
      "final": ["Design", "Develop", "Integrate"]}
AV = ["Demonstrate diligence in", "Value precision in", "Show commitment to",
      "Demonstrate persistence in", "Value collaboration in", "Demonstrate professionalism in"]


def _period_info(wk: int):
    if wk <= 6:
        return ("PRELIM EXAM" if wk == 6 else "PRELIM"), "prelim", wk == 6
    if wk <= 12:
        return ("MIDTERM EXAM" if wk == 12 else "MIDTERM"), "midterm", wk == 12
    return ("FINAL EXAM" if wk == 18 else "FINAL"), "final", wk == 18


def _llos(topic: str, stage: str, idx: int):
    k = KV[stage][idx % len(KV[stage])]
    s = SV[stage][idx % len(SV[stage])]
    a = AV[idx % len(AV)]
    return [
        {"category": "K", "outcome_text": f"{k} the key concepts of {topic}."},
        {"category": "S", "outcome_text": f"{s} techniques related to {topic} through hands-on practice."},
        {"category": "A", "outcome_text": f"{a} completing {topic.lower()} activities."},
    ]


def _exam_llos():
    return [
        {"category": "K", "outcome_text": "Recall and synthesize key concepts covered in the preceding weeks."},
        {"category": "S", "outcome_text": "Apply learned skills to solve assessment items accurately."},
        {"category": "A", "outcome_text": "Demonstrate academic integrity and diligence during examination."},
    ]


def generate_mock_payload(course_key: str, course_code: str = None, instructor: str = "(Instructor Name)",
                           section: str = "(Section)", school_year: str = "2026-2027",
                           semester: str = "1st Semester") -> dict:
    """Builds a full schema-valid syllabus dict for one of the 5 CCS subjects."""
    src = COURSES[course_key]
    course_outcomes = [
        {"clo_number": i + 1, "bloom_level": b, "co_description": d, "mapped_po": po}
        for i, (b, d, po) in enumerate(src["clos"])
    ]
    n_clos = len(course_outcomes)

    weekly_schedule = []
    for i, topic in enumerate(src["weeks"]):
        wk = i + 1
        label, stage, is_exam = _period_info(wk)
        period = label.replace(" EXAM", "")
        llos = _exam_llos() if is_exam else _llos(topic, stage, i)
        tla = "Written/Practical Examination" if is_exam else "Lecture, Discussion & Hands-on Laboratory Exercise"
        assess = "Examination Paper" if is_exam else "Quiz, Seatwork & Lab Rubric"
        evid = "Exam Results" if is_exam else "Output, Report & Executable Artifact"
        aligned = [1 + (i % n_clos)] if not is_exam else [1 + (i % n_clos)]
        weekly_schedule.append({
            "week_number": wk,
            "period": period,
            "topics": [topic],
            "llos": llos,
            "teaching_learning_activity": tla,
            "assessment_tool": assess,
            "evidence": evid,
            "aligned_co": aligned,
        })

    # Guarantee every declared CLO is referenced at least once (schema cross-check).
    referenced = {n for wk in weekly_schedule for n in wk["aligned_co"]}
    missing = set(range(1, n_clos + 1)) - referenced
    for j, clo_num in enumerate(sorted(missing)):
        weekly_schedule[j]["aligned_co"].append(clo_num)

    return {
        "course_code": course_code or src["default_code"],
        "course_title": src["title"],
        "instructor": instructor,
        "section": section,
        "school_year": school_year,
        "semester": semester,
        "course_outcomes": course_outcomes,
        "grading_breakdown": {
            "quizzes_pct": 30.0, "research_pct": 20.0, "seatwork_lab_pct": 50.0,
            "class_standing_weight": 70.0, "major_exam_weight": 30.0,
        },
        "weekly_schedule": weekly_schedule,
    }
