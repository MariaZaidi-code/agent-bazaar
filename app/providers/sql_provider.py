from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from app.providers.base import BaseProvider

ALLOWED_TABLES = {"students", "courses", "enrollments", "faculty"}
PROGRAMS = [
    "BS Artificial Intelligence",
    "BS Computer Science",
    "BS Data Science",
    "BS Software Engineering",
]


def ensure_sample_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                program TEXT NOT NULL,
                enrollment_year INTEGER NOT NULL,
                gpa REAL NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                credits INTEGER NOT NULL,
                department TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                term TEXT NOT NULL,
                grade TEXT,
                FOREIGN KEY(student_id) REFERENCES students(id),
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );
            CREATE TABLE IF NOT EXISTS faculty (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                title TEXT NOT NULL
            );
            """
        )
        count = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if count:
            return
        students = [
            ("Ayesha Khan", PROGRAMS[0], 2023, 3.82, "active"),
            ("Bilal Ahmed", PROGRAMS[0], 2023, 3.45, "active"),
            ("Hira Fatima", PROGRAMS[0], 2023, 3.91, "active"),
            ("Usman Ali", PROGRAMS[0], 2022, 3.12, "active"),
            ("Zainab Raza", PROGRAMS[0], 2022, 3.68, "active"),
            ("Ahmed Raza", PROGRAMS[0], 2024, 3.27, "active"),
            ("Noor ul Ain", PROGRAMS[0], 2024, 3.74, "active"),
            ("Hamza Sheikh", PROGRAMS[1], 2022, 3.55, "active"),
            ("Fatima Noor", PROGRAMS[1], 2023, 3.21, "active"),
            ("Ali Hassan", PROGRAMS[1], 2023, 2.98, "active"),
            ("Sara Iqbal", PROGRAMS[1], 2024, 3.62, "active"),
            ("Muhammad Daniyal", PROGRAMS[1], 2024, 3.08, "active"),
            ("Areeba Shah", PROGRAMS[2], 2022, 3.88, "active"),
            ("Talha Javed", PROGRAMS[2], 2023, 3.31, "active"),
            ("Mahnoor Aslam", PROGRAMS[2], 2024, 3.59, "active"),
            ("Ibrahim Yousaf", PROGRAMS[3], 2022, 3.17, "active"),
            ("Khadija Imran", PROGRAMS[3], 2023, 3.73, "active"),
            ("Rayan Malik", PROGRAMS[3], 2024, 3.42, "active"),
            ("Laiba Tariq", PROGRAMS[3], 2024, 3.05, "active"),
            ("Zohaib Akram", PROGRAMS[0], 2021, 2.84, "graduated"),
        ]
        connection.executemany(
            """
            INSERT INTO students (name, program, enrollment_year, gpa, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            students,
        )
        courses = [
            ("AI101", "Introduction to Artificial Intelligence", 3, "Artificial Intelligence"),
            ("AI201", "Machine Learning", 3, "Artificial Intelligence"),
            ("AI301", "Knowledge Graphs and Ontologies", 3, "Artificial Intelligence"),
            ("AI302", "Multi-Agent Systems", 3, "Artificial Intelligence"),
            ("CS101", "Programming Fundamentals", 4, "Computer Science"),
            ("CS201", "Data Structures", 4, "Computer Science"),
            ("DS201", "Data Mining", 3, "Data Science"),
            ("SE201", "Software Design", 3, "Software Engineering"),
        ]
        connection.executemany(
            "INSERT INTO courses (code, title, credits, department) VALUES (?, ?, ?, ?)",
            courses,
        )
        enrollments = [
            (1, 1, "Fall 2025", "A"),
            (1, 2, "Fall 2025", "A-"),
            (2, 1, "Fall 2025", "B+"),
            (2, 2, "Fall 2025", "B"),
            (3, 1, "Fall 2025", "A"),
            (3, 3, "Fall 2025", "A-"),
            (4, 4, "Fall 2025", "B-"),
            (5, 3, "Fall 2025", "A-"),
            (6, 1, "Fall 2025", "B"),
            (7, 2, "Fall 2025", "A-"),
            (8, 5, "Fall 2025", "B+"),
            (8, 6, "Fall 2025", "B"),
            (9, 6, "Fall 2025", "B-"),
            (10, 5, "Fall 2025", "C+"),
            (11, 7, "Fall 2025", "A-"),
            (12, 7, "Fall 2025", "B"),
            (13, 7, "Fall 2025", "A"),
            (14, 7, "Fall 2025", "B+"),
            (15, 8, "Fall 2025", "A-"),
            (16, 8, "Fall 2025", "B"),
            (17, 8, "Fall 2025", "A"),
            (18, 5, "Fall 2025", "B"),
            (19, 5, "Fall 2025", "B-"),
        ]
        connection.executemany(
            """
            INSERT INTO enrollments (student_id, course_id, term, grade)
            VALUES (?, ?, ?, ?)
            """,
            enrollments,
        )
        faculty = [
            ("Dr. Sana Malik", "Artificial Intelligence", "Associate Professor"),
            ("Dr. Omar Farooq", "Computer Science", "Professor"),
            ("Dr. Hina Aslam", "Data Science", "Assistant Professor"),
            ("Dr. Faisal Nadeem", "Software Engineering", "Assistant Professor"),
        ]
        connection.executemany(
            "INSERT INTO faculty (name, department, title) VALUES (?, ?, ?)",
            faculty,
        )
        connection.commit()
    finally:
        connection.close()


class UniversitySQLProvider(BaseProvider):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        ensure_sample_database(self.settings.sample_sql_db)

    @staticmethod
    def _program_from_question(question: str) -> str | None:
        lowered = question.lower()
        if "artificial intelligence" in lowered or "bs ai" in lowered or " ai " in f" {lowered} ":
            return PROGRAMS[0]
        if "computer science" in lowered or "bs cs" in lowered or " cs " in f" {lowered} ":
            return PROGRAMS[1]
        if "data science" in lowered or "bs ds" in lowered or " ds " in f" {lowered} ":
            return PROGRAMS[2]
        if "software engineering" in lowered or "bs se" in lowered or " se " in f" {lowered} ":
            return PROGRAMS[3]
        return None

    def _generate_sql(self, question: str) -> tuple[str, list[Any]]:
        lowered = question.lower()
        program = self._program_from_question(question)
        if re.search(r"(average|avg|mean)\s+(gpa|grade)", lowered):
            if program:
                return (
                    "SELECT ROUND(AVG(gpa), 2) AS average_gpa, COUNT(*) AS students "
                    "FROM students WHERE program = ?",
                    [program],
                )
            return (
                "SELECT ROUND(AVG(gpa), 2) AS average_gpa, COUNT(*) AS students FROM students",
                [],
            )
        top_match = re.search(r"top\s+(\d+)\s+students?", lowered)
        if top_match:
            limit = max(1, min(20, int(top_match.group(1))))
            if program:
                return (
                    "SELECT name, program, gpa FROM students WHERE program = ? "
                    "ORDER BY gpa DESC LIMIT ?",
                    [program, limit],
                )
            return (
                "SELECT name, program, gpa FROM students ORDER BY gpa DESC LIMIT ?",
                [limit],
            )
        if "most popular" in lowered or "most enrolled" in lowered or "enrolment by course" in lowered:
            return (
                "SELECT c.code, c.title, COUNT(e.id) AS enrolled "
                "FROM courses c JOIN enrollments e ON e.course_id = c.id "
                "GROUP BY c.id ORDER BY enrolled DESC LIMIT 10",
                [],
            )
        if "faculty" in lowered or "teacher" in lowered or "professor" in lowered:
            return "SELECT name, department, title FROM faculty ORDER BY name", []
        if "course" in lowered and "students" not in lowered:
            return (
                "SELECT code, title, credits, department FROM courses ORDER BY code",
                [],
            )
        if "enrol" in lowered and program:
            return (
                "SELECT COUNT(*) AS students FROM students WHERE program = ?",
                [program],
            )
        if "student" in lowered and ("count" in lowered or "how many" in lowered or "number" in lowered):
            if program:
                return (
                    "SELECT COUNT(*) AS students FROM students WHERE program = ?",
                    [program],
                )
            return (
                "SELECT program, COUNT(*) AS students FROM students "
                "GROUP BY program ORDER BY students DESC",
                [],
            )
        if program:
            return (
                "SELECT program, COUNT(*) AS students, ROUND(AVG(gpa), 2) AS average_gpa "
                "FROM students WHERE program = ? GROUP BY program",
                [program],
            )
        return (
            "SELECT program, COUNT(*) AS students, ROUND(AVG(gpa), 2) AS average_gpa "
            "FROM students GROUP BY program ORDER BY students DESC",
            [],
        )

    @staticmethod
    def _guard_sql(sql: str) -> str:
        stripped = sql.strip().rstrip(";")
        if ";" in stripped or "--" in stripped or "/*" in stripped:
            raise ValueError("SQL contains a forbidden separator or comment")
        if not re.match(r"^(select|with)\b", stripped, re.I):
            raise ValueError("only SELECT queries are allowed")
        if re.search(
            r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|replace|trigger)\b",
            stripped,
            re.I,
        ):
            raise ValueError("SQL contains a forbidden keyword")
        for table in re.findall(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", stripped, re.I):
            if table.lower() not in ALLOWED_TABLES:
                raise ValueError(f"table {table} is not allow-listed")
        return stripped

    def _run(self, params: dict[str, Any]) -> dict[str, Any]:
        question = str(params.get("question", "")).strip()
        if not question:
            raise ValueError("question is required")
        sql, sql_params = self._generate_sql(question)
        safe_sql = self._guard_sql(sql)
        uri = f"file:{self.settings.sample_sql_db}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            cursor = connection.execute(safe_sql, sql_params)
            columns = [column[0] for column in cursor.description or []]
            rows = [dict(row) for row in cursor.fetchmany(100)]
        finally:
            connection.close()
        return {
            "table": {
                "columns": columns,
                "rows": rows,
                "sql": safe_sql,
                "row_count": len(rows),
            }
        }

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._run(params)

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._run(params)
