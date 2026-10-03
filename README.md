# Automated Rollback for Online Examination System

A starter Flask + SQLite project with admin/student roles, exam creation, per-exam question limits, checkpoints, rollback, timer, results, and failure logs.

## Requirements
- Python 3.10 or newer
- VS Code
- Flask (installed from `requirements.txt`)
- A browser

## Run in VS Code (Windows)
1. Extract the ZIP.
2. Open the extracted `automated_rollback_exam` folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   ```
5. Install packages:
   ```powershell
   pip install -r requirements.txt
   ```
6. Run:
   ```powershell
   python app.py
   ```
7. Open `http://127.0.0.1:5000` in your browser.

## First admin login
- Username: `admin`
- Password: `Admin@123`

Change the default admin password before using this beyond a local demo. This starter app does not yet include a password-change screen.

## Give students access from another computer on the same Wi-Fi/LAN
1. Run the app on the host computer using `python app.py`.
2. Find that computer's local IPv4 address with `ipconfig` on Windows.
3. On that computer, allow Python through Windows Firewall on a **private network** if prompted.
4. On the student computer, open `http://HOST-COMPUTER-IP:5000` (replace the example with the host computer's IPv4 address).
5. Log in with a student account created by the admin in the dashboard.

This is intended for a classroom/demo LAN. Do not expose Flask's development server directly to the public internet. For public deployment, use a production WSGI server, HTTPS, a strong secret key, CSRF protection, and proper server/database backups.

## Features
- Admin and student login with role-based access.
- Admin creates student accounts.
- Admin creates exams with duration and question limit.
- Question count is capped at the exam's configured limit.
- Admin can delete questions and exams.
- Students take exams, navigate questions, and submit answers.
- Server-side checkpoints every 10 seconds and when an answer changes.
- Local browser checkpoint fallback and rollback UI for simulated failure/network reconnect.
- Results are calculated and displayed after submission.
- Admin can inspect attempt statuses and failure logs.

## Rollback note
The server checkpoint preserves the most recently saved answer state, current question, and remaining time. A browser cannot reliably detect every kind of crash, and a timer running in a browser can be manipulated. For a real high-stakes examination, add server-authoritative timing, audit logs, backups, secure deployment, and stronger anti-tampering controls.
