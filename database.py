import sqlite3
import os
from werkzeug.security import generate_password_hash

DATABASE = 'brainova.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    conn.commit()

    # Migration: add `difficulty` to questions if missing (existing DBs)
    cols = [r['name'] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
    if 'difficulty' not in cols:
        conn.execute("ALTER TABLE questions ADD COLUMN difficulty INTEGER")
        conn.commit()

    # Migration: link test_results back to the admin-defined test that produced
    # them (NULL for the legacy / quick-start Brainova test).
    result_cols = [r['name'] for r in conn.execute("PRAGMA table_info(test_results)").fetchall()]
    if 'test_id' not in result_cols:
        conn.execute("ALTER TABLE test_results ADD COLUMN test_id INTEGER REFERENCES tests(id)")
        conn.commit()

    # Create default admin user if none exists
    admin = conn.execute("SELECT id FROM users WHERE is_admin = 1").fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, 1)",
            ('admin', 'admin@brainova.com', generate_password_hash('admin123'))
        )
        conn.commit()

    # Seed sample questions if none exist
    count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if count == 0:
        _seed_questions(conn)

    conn.close()


def _seed_questions(conn):
    sample = [
        # Logical
        ("If all Bloops are Razzles and all Razzles are Lazzles, then all Bloops are definitely Lazzles?",
         "logical",
         [("True", True), ("False", False), ("Cannot determine", False), ("Sometimes", False), ("Never", False)]),
        ("Which number comes next: 2, 4, 8, 16, __?",
         "logical",
         [("24", False), ("32", True), ("30", False), ("28", False), ("36", False)]),
        ("A is taller than B. C is shorter than A. B is taller than C. Who is tallest?",
         "logical",
         [("B", False), ("C", False), ("A", True), ("Cannot determine", False), ("All equal", False)]),

        # Numerical
        ("What is 15% of 200?",
         "numerical",
         [("25", False), ("30", True), ("35", False), ("20", False), ("40", False)]),
        ("If a train travels 60 km in 45 minutes, what is its speed in km/h?",
         "numerical",
         [("70", False), ("75", False), ("80", True), ("85", False), ("90", False)]),
        ("What is the next number: 1, 4, 9, 16, 25, __?",
         "numerical",
         [("30", False), ("36", True), ("32", False), ("49", False), ("35", False)]),

        # Verbal
        ("Choose the word most similar in meaning to BENEVOLENT:",
         "verbal",
         [("Cruel", False), ("Kind", True), ("Angry", False), ("Lazy", False), ("Loud", False)]),
        ("BOOK is to LIBRARY as PAINTING is to:",
         "verbal",
         [("Canvas", False), ("Artist", False), ("Gallery", True), ("Brush", False), ("Frame", False)]),
        ("Which word does NOT belong? Dog, Cat, Rose, Fish",
         "verbal",
         [("Dog", False), ("Cat", False), ("Rose", True), ("Fish", False), ("None", False)]),

        # Spatial
        ("How many sides does a hexagon have?",
         "spatial",
         [("5", False), ("6", True), ("7", False), ("8", False), ("4", False)]),
        ("If you fold a square piece of paper in half diagonally, what shape do you get?",
         "spatial",
         [("Square", False), ("Rectangle", False), ("Triangle", True), ("Pentagon", False), ("Circle", False)]),
        ("A cube has how many edges?",
         "spatial",
         [("8", False), ("10", False), ("12", True), ("6", False), ("16", False)]),
    ]

    for q_text, category, opts in sample:
        cur = conn.execute(
            "INSERT INTO questions (question_text, category) VALUES (?, ?)",
            (q_text, category)
        )
        q_id = cur.lastrowid
        for opt_text, is_correct in opts:
            conn.execute(
                "INSERT INTO answers (question_id, option_text, is_correct) VALUES (?, ?, ?)",
                (q_id, opt_text, 1 if is_correct else 0)
            )
    conn.commit()
