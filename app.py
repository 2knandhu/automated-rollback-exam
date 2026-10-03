import json
import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "exam_system.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','student')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            duration INTEGER NOT NULL,
            question_limit INTEGER NOT NULL,
            is_published INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option INTEGER NOT NULL CHECK(correct_option BETWEEN 0 AND 3),
            FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'in_progress',
            score INTEGER,
            current_question INTEGER NOT NULL DEFAULT 0,
            answers_json TEXT NOT NULL DEFAULT '{}',
            remaining_time INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, exam_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS failure_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exam_id INTEGER,
            failure_type TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE SET NULL
        );
        """)
        admin = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if not admin:
            db.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                ("admin", generate_password_hash("Admin@123"), "admin", datetime.now().isoformat(timespec="seconds"))
            )


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You do not have permission to access that page.", "error")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/")
def index():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "student_dashboard"))


@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    with get_db() as db:
        exams = db.execute("""
            SELECT e.*, (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) AS question_count
            FROM exams e ORDER BY e.id DESC
        """).fetchall()
        students = db.execute("SELECT id,username,created_at FROM users WHERE role='student' ORDER BY id DESC").fetchall()
        attempts = db.execute("""
            SELECT a.*, u.username, e.title FROM attempts a
            JOIN users u ON u.id=a.user_id JOIN exams e ON e.id=a.exam_id
            ORDER BY a.updated_at DESC LIMIT 30
        """).fetchall()
        logs = db.execute("""
            SELECT f.*, u.username, e.title FROM failure_logs f
            LEFT JOIN users u ON u.id=f.user_id LEFT JOIN exams e ON e.id=f.exam_id
            ORDER BY f.id DESC LIMIT 30
        """).fetchall()
    return render_template("admin_dashboard.html", exams=exams, students=students, attempts=attempts, logs=logs)


@app.route("/admin/students/create", methods=["POST"])
@login_required("admin")
def create_student():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if len(username) < 3 or len(password) < 6:
        flash("Student username must be at least 3 characters and password at least 6 characters.", "error")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                (username, generate_password_hash(password), "student", datetime.now().isoformat(timespec="seconds"))
            )
        flash("Student account created. Share the login details securely.", "success")
    except sqlite3.IntegrityError:
        flash("That username already exists.", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/exams/create", methods=["POST"])
@login_required("admin")
def create_exam():
    title = request.form.get("title", "").strip()
    try:
        duration = int(request.form.get("duration", "0"))
        question_limit = int(request.form.get("question_limit", "0"))
    except ValueError:
        duration, question_limit = 0, 0
    if not title or duration < 1 or question_limit < 1:
        flash("Enter an exam title, duration of at least 1 minute, and question limit of at least 1.", "error")
        return redirect(url_for("admin_dashboard"))
    with get_db() as db:
        db.execute(
            "INSERT INTO exams(title,duration,question_limit,is_published,created_at) VALUES(?,?,?,?,?)",
            (title, duration, question_limit, 1, datetime.now().isoformat(timespec="seconds"))
        )
    flash("Exam created.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/exams/<int:exam_id>/questions", methods=["GET", "POST"])
@login_required("admin")
def manage_questions(exam_id):
    with get_db() as db:
        exam = db.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
        if not exam:
            abort(404)
        if request.method == "POST":
            count = db.execute("SELECT COUNT(*) AS n FROM questions WHERE exam_id=?", (exam_id,)).fetchone()["n"]
            if count >= exam["question_limit"]:
                flash("Question limit reached. Increase the limit or delete a question before adding more.", "error")
                return redirect(url_for("manage_questions", exam_id=exam_id))
            values = [
                request.form.get("question", "").strip(),
                request.form.get("option_a", "").strip(),
                request.form.get("option_b", "").strip(),
                request.form.get("option_c", "").strip(),
                request.form.get("option_d", "").strip()
            ]
            try:
                correct = int(request.form.get("correct_option", "-1"))
            except ValueError:
                correct = -1
            if not all(values) or correct not in range(4):
                flash("Fill in the question, all four options, and correct answer.", "error")
            else:
                db.execute("""
                    INSERT INTO questions(exam_id,question,option_a,option_b,option_c,option_d,correct_option)
                    VALUES(?,?,?,?,?,?,?)
                """, (exam_id, *values, correct))
                flash("Question added.", "success")
                return redirect(url_for("manage_questions", exam_id=exam_id))
        questions = db.execute("SELECT * FROM questions WHERE exam_id=? ORDER BY id", (exam_id,)).fetchall()
        count = len(questions)
    return render_template("manage_questions.html", exam=exam, questions=questions, count=count)


@app.route("/admin/questions/<int:question_id>/delete", methods=["POST"])
@login_required("admin")
def delete_question(question_id):
    with get_db() as db:
        q = db.execute("SELECT exam_id FROM questions WHERE id=?", (question_id,)).fetchone()
        if q:
            exam_id = q["exam_id"]
            db.execute("DELETE FROM questions WHERE id=?", (question_id,))
            flash("Question deleted.", "success")
            return redirect(url_for("manage_questions", exam_id=exam_id))
    flash("Question not found.", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/exams/<int:exam_id>/delete", methods=["POST"])
@login_required("admin")
def delete_exam(exam_id):
    with get_db() as db:
        db.execute("DELETE FROM exams WHERE id=?", (exam_id,))
    flash("Exam and its related questions/attempts were deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/student")
@login_required("student")
def student_dashboard():
    with get_db() as db:
        exams = db.execute("""
            SELECT e.*,
              (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) AS question_count,
              a.status AS attempt_status, a.score AS attempt_score
            FROM exams e
            LEFT JOIN attempts a ON a.exam_id=e.id AND a.user_id=?
            WHERE e.is_published=1 ORDER BY e.id DESC
        """, (session["user_id"],)).fetchall()
    return render_template("student_dashboard.html", exams=exams)


def get_attempt(db, user_id, exam):
    attempt = db.execute("SELECT * FROM attempts WHERE user_id=? AND exam_id=?", (user_id, exam["id"])).fetchone()
    if not attempt:
        db.execute("""
            INSERT INTO attempts(user_id,exam_id,status,score,current_question,answers_json,remaining_time,updated_at)
            VALUES(?,?,'in_progress',NULL,0,'{}',?,?)
        """, (user_id, exam["id"], exam["duration"] * 60, datetime.now().isoformat(timespec="seconds")))
        attempt = db.execute("SELECT * FROM attempts WHERE user_id=? AND exam_id=?", (user_id, exam["id"])).fetchone()
    return attempt


@app.route("/exam/<int:exam_id>", methods=["GET", "POST"])
@login_required("student")
def take_exam(exam_id):
    with get_db() as db:
        exam = db.execute("SELECT * FROM exams WHERE id=? AND is_published=1", (exam_id,)).fetchone()
        if not exam:
            abort(404)
        questions = db.execute("SELECT * FROM questions WHERE exam_id=? ORDER BY id LIMIT ?", (exam_id, exam["question_limit"])).fetchall()
        if not questions:
            flash("This exam has no questions yet.", "error")
            return redirect(url_for("student_dashboard"))
        attempt = get_attempt(db, session["user_id"], exam)
        if attempt["status"] == "submitted":
            flash("You have already submitted this exam.", "error")
            return redirect(url_for("student_dashboard"))
        if request.method == "POST":
            try:
                submitted_answers = json.loads(request.form.get("answers", "{}"))
                if not isinstance(submitted_answers, dict):
                    submitted_answers = {}
            except (ValueError, TypeError):
                submitted_answers = {}
            score = 0
            for q in questions:
                if str(q["id"]) in submitted_answers:
                    try:
                        if int(submitted_answers[str(q["id"])]) == q["correct_option"]:
                            score += 1
                    except (ValueError, TypeError):
                        pass
            db.execute("""
                UPDATE attempts SET status='submitted',score=?,answers_json=?,updated_at=?
                WHERE user_id=? AND exam_id=?
            """, (score, json.dumps(submitted_answers), datetime.now().isoformat(timespec="seconds"), session["user_id"], exam_id))
            flash(f"Exam submitted. Your score is {score}/{len(questions)}.", "success")
            return redirect(url_for("student_dashboard"))
        try:
            checkpoint = json.loads(attempt["answers_json"] or "{}")
        except ValueError:
            checkpoint = {}
        checkpoint_data = {
            "answers": checkpoint,
            "current_question": attempt["current_question"],
            "remaining_time": attempt["remaining_time"]
        }
    return render_template("take_exam.html", exam=exam, questions=questions, attempt=attempt, checkpoint=checkpoint_data)


@app.route("/api/checkpoint", methods=["POST"])
@login_required("student")
def save_checkpoint():
    data = request.get_json(silent=True) or {}
    try:
        exam_id = int(data.get("exam_id"))
        current_question = max(0, int(data.get("current_question", 0)))
        remaining_time = max(0, int(data.get("remaining_time", 0)))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Invalid checkpoint data"), 400
    answers = data.get("answers", {})
    if not isinstance(answers, dict):
        answers = {}
    with get_db() as db:
        exam = db.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
        if not exam:
            return jsonify(ok=False, error="Exam not found"), 404
        attempt = db.execute("SELECT * FROM attempts WHERE user_id=? AND exam_id=?", (session["user_id"], exam_id)).fetchone()
        if not attempt or attempt["status"] != "in_progress":
            return jsonify(ok=False, error="No active attempt"), 409
        question_ids = {str(r["id"]) for r in db.execute("SELECT id FROM questions WHERE exam_id=?", (exam_id,)).fetchall()}
        answers = {str(k): int(v) for k, v in answers.items() if str(k) in question_ids and str(v).isdigit() and int(v) in range(4)}
        current_question = min(current_question, max(0, exam["question_limit"] - 1))
        db.execute("""
            UPDATE attempts SET current_question=?,answers_json=?,remaining_time=?,updated_at=?
            WHERE id=?
        """, (current_question, json.dumps(answers), remaining_time, datetime.now().isoformat(timespec="seconds"), attempt["id"]))
    return jsonify(ok=True)


@app.route("/api/failure", methods=["POST"])
@login_required("student")
def log_failure():
    data = request.get_json(silent=True) or {}
    try:
        exam_id = int(data.get("exam_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Invalid exam id"), 400
    failure_type = str(data.get("failure_type", "Unexpected interruption"))[:100]
    with get_db() as db:
        attempt = db.execute("SELECT * FROM attempts WHERE user_id=? AND exam_id=?", (session["user_id"], exam_id)).fetchone()
        if not attempt:
            return jsonify(ok=False, error="Attempt not found"), 404
        db.execute(
            "INSERT INTO failure_logs(user_id,exam_id,failure_type,details,created_at) VALUES(?,?,?,?,?)",
            (session["user_id"], exam_id, failure_type, "Restored from most recent server checkpoint", datetime.now().isoformat(timespec="seconds"))
        )
        try:
            answers = json.loads(attempt["answers_json"] or "{}")
        except ValueError:
            answers = {}
        return jsonify(ok=True, answers=answers, current_question=attempt["current_question"], remaining_time=attempt["remaining_time"])


@app.route("/health")
def health():
    return jsonify(status="ok")


init_db()

if __name__ == "__main__":
    # Use host=0.0.0.0 to allow access from other devices on the same network.
    app.run(host="0.0.0.0", port=5000, debug=True)
