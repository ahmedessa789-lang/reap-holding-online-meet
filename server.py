from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
from pathlib import Path
import sqlite3
import json
import secrets
import hashlib
import os
import mimetypes
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "meetings.db"
PORT = int(os.environ.get("PORT", "8005"))

TOKENS = {}

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def row_to_dict(row):
    return dict(row) if row else None

def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            department TEXT NOT NULL DEFAULT 'General',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            department TEXT NOT NULL,
            meeting_date TEXT,
            meeting_time TEXT,
            duration INTEGER NOT NULL DEFAULT 60,
            host_name TEXT NOT NULL,
            participants TEXT,
            agenda TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'Scheduled',
            created_by INTEGER,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """)

    cur.execute("SELECT COUNT(*) AS count FROM users")
    if cur.fetchone()["count"] == 0:
        now = datetime.now().isoformat(timespec="seconds")
        demo_users = [
            ("Ahmed Eissa", "admin@reapholding.com", "admin123", "admin", "Management"),
            ("Reap User", "user@reapholding.com", "user123", "user", "General"),
        ]
        for name, email, password, role, department in demo_users:
            cur.execute("""
                INSERT INTO users (name, email, password_hash, role, department, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, email, hash_password(password), role, department, now))

    conn.commit()
    conn.close()

def make_room_id(title: str) -> str:
    clean = "".join(ch if ch.isalnum() else "-" for ch in title).strip("-")
    clean = "-".join(part for part in clean.split("-") if part)[:28] or "Meeting"
    return f"Reap-Holding-{clean}-{secrets.randbelow(90000) + 10000}"

class AppHandler(BaseHTTPRequestHandler):
    server_version = "ReapHoldingOnlineMeet/2.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            return self.serve_file(STATIC_DIR / "index.html")

        if path.startswith("/api/"):
            return self.handle_api_get(path)

        file_path = STATIC_DIR / path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            return self.serve_file(file_path)

        return self.not_found("File not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            return self.handle_api_post(path)
        return self.not_found("Endpoint not found")

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            return self.handle_api_patch(path)
        return self.not_found("Endpoint not found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            return self.handle_api_delete(path)
        return self.not_found("Endpoint not found")

    def handle_api_get(self, path):
        if path == "/api/health":
            return self.json_response({"status": "ok", "app": "Reap Holding Online Meet V2"})

        if path == "/api/me":
            user = self.current_user()
            if not user:
                return self.unauthorized()
            return self.json_response({"user": user})

        if path == "/api/admin/users":
            user = self.current_user()
            if not user:
                return self.unauthorized()
            if user["role"] != "admin":
                return self.forbidden("Admin access required")

            conn = db()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, email, role, department, created_at
                FROM users
                ORDER BY id DESC
            """)
            rows = [row_to_dict(r) for r in cur.fetchall()]
            conn.close()
            return self.json_response({"users": rows})

        if path == "/api/admin/stats":
            user = self.current_user()
            if not user:
                return self.unauthorized()
            if user["role"] != "admin":
                return self.forbidden("Admin access required")

            conn = db()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS count FROM meetings")
            total_meetings = cur.fetchone()["count"]

            cur.execute("SELECT COALESCE(SUM(duration), 0) AS minutes FROM meetings")
            total_minutes = cur.fetchone()["minutes"]

            cur.execute("SELECT COUNT(DISTINCT department) AS count FROM meetings")
            departments = cur.fetchone()["count"]

            cur.execute("""
                SELECT department, COUNT(*) AS count, COALESCE(SUM(duration), 0) AS minutes
                FROM meetings
                GROUP BY department
                ORDER BY count DESC
            """)
            usage = [row_to_dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT m.*, u.name AS created_by_name
                FROM meetings m
                LEFT JOIN users u ON u.id = m.created_by
                ORDER BY m.id DESC LIMIT 8
            """)
            recent = [row_to_dict(r) for r in cur.fetchall()]
            conn.close()

            return self.json_response({
                "total_meetings": total_meetings,
                "total_hours": round(total_minutes / 60, 1),
                "departments": departments,
                "usage": usage,
                "recent": recent,
            })

        if path == "/api/meetings":
            user = self.current_user()
            if not user:
                return self.unauthorized()
            conn = db()
            cur = conn.cursor()
            if user["role"] == "admin":
                cur.execute("""
                    SELECT m.*, u.name AS created_by_name
                    FROM meetings m
                    LEFT JOIN users u ON u.id = m.created_by
                    ORDER BY m.id DESC
                """)
            else:
                cur.execute("""
                    SELECT m.*, u.name AS created_by_name
                    FROM meetings m
                    LEFT JOIN users u ON u.id = m.created_by
                    WHERE m.created_by = ?
                    ORDER BY m.id DESC
                """, (user["id"],))
            rows = [row_to_dict(r) for r in cur.fetchall()]
            conn.close()
            return self.json_response({"meetings": rows})

        if path.startswith("/api/meetings/"):
            user = self.current_user()
            if not user:
                return self.unauthorized()
            room_id = unquote(path.split("/api/meetings/", 1)[1])
            conn = db()
            cur = conn.cursor()
            cur.execute("""
                SELECT m.*, u.name AS created_by_name
                FROM meetings m
                LEFT JOIN users u ON u.id = m.created_by
                WHERE m.room_id = ?
            """, (room_id,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return self.not_found("Meeting not found")
            return self.json_response({"meeting": row_to_dict(row)})

        return self.not_found("Endpoint not found")

    def handle_api_post(self, path):
        if path == "/api/login":
            data = self.read_json()
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""

            conn = db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email = ?", (email,))
            user_row = cur.fetchone()
            conn.close()

            if not user_row or user_row["password_hash"] != hash_password(password):
                return self.bad_request("Invalid email or password")

            user = row_to_dict(user_row)
            token = secrets.token_urlsafe(32)
            TOKENS[token] = user["id"]

            safe_user = {k: user[k] for k in ["id", "name", "email", "role", "department"]}
            return self.json_response({"token": token, "user": safe_user})

        if path == "/api/register":
            data = self.read_json()
            name = (data.get("name") or "").strip()
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""
            department = (data.get("department") or "General").strip()

            if not name:
                return self.bad_request("User name is required")
            if not email or "@" not in email:
                return self.bad_request("Valid email is required")
            if len(password) < 6:
                return self.bad_request("Password must be at least 6 characters")

            conn = db()
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO users (name, email, password_hash, role, department, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    email,
                    hash_password(password),
                    "user",
                    department,
                    datetime.now().isoformat(timespec="seconds"),
                ))
                conn.commit()
                user_id = cur.lastrowid
                cur.execute("""
                    SELECT id, name, email, role, department, created_at
                    FROM users WHERE id = ?
                """, (user_id,))
                new_user = row_to_dict(cur.fetchone())
                conn.close()
                return self.json_response({"user": new_user}, status=201)
            except sqlite3.IntegrityError:
                conn.close()
                return self.bad_request("Email already exists")

        if path == "/api/logout":
            token = self.get_token()
            if token and token in TOKENS:
                del TOKENS[token]
            return self.json_response({"ok": True})

        if path == "/api/admin/users":
            user = self.current_user()
            if not user:
                return self.unauthorized()
            if user["role"] != "admin":
                return self.forbidden("Admin access required")

            data = self.read_json()
            name = (data.get("name") or "").strip()
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""
            role = (data.get("role") or "user").strip().lower()
            department = (data.get("department") or "General").strip()

            if not name:
                return self.bad_request("User name is required")
            if not email or "@" not in email:
                return self.bad_request("Valid email is required")
            if len(password) < 6:
                return self.bad_request("Password must be at least 6 characters")
            if role not in {"admin", "user"}:
                return self.bad_request("Invalid role")

            conn = db()
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO users (name, email, password_hash, role, department, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    email,
                    hash_password(password),
                    role,
                    department,
                    datetime.now().isoformat(timespec="seconds"),
                ))
                conn.commit()
                user_id = cur.lastrowid
                cur.execute("""
                    SELECT id, name, email, role, department, created_at
                    FROM users WHERE id = ?
                """, (user_id,))
                new_user = row_to_dict(cur.fetchone())
                conn.close()
                return self.json_response({"user": new_user}, status=201)
            except sqlite3.IntegrityError:
                conn.close()
                return self.bad_request("Email already exists")

        if path == "/api/meetings":
            user = self.current_user()
            if not user:
                return self.unauthorized()

            data = self.read_json()
            title = (data.get("title") or "").strip()
            host_name = (data.get("host_name") or user["name"]).strip()

            if not title:
                return self.bad_request("Meeting title is required")
            if not host_name:
                return self.bad_request("Host name is required")

            room_id = make_room_id(title)
            now = datetime.now().isoformat(timespec="seconds")

            conn = db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO meetings (
                    room_id, title, department, meeting_date, meeting_time, duration,
                    host_name, participants, agenda, notes, status, created_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                room_id,
                title,
                data.get("department") or user["department"] or "General",
                data.get("meeting_date") or "",
                data.get("meeting_time") or "",
                int(data.get("duration") or 60),
                host_name,
                data.get("participants") or "",
                data.get("agenda") or "",
                data.get("notes") or "",
                data.get("status") or "Scheduled",
                user["id"],
                now,
            ))
            conn.commit()
            cur.execute("""
                SELECT m.*, u.name AS created_by_name
                FROM meetings m
                LEFT JOIN users u ON u.id = m.created_by
                WHERE m.room_id = ?
            """, (room_id,))
            meeting = row_to_dict(cur.fetchone())
            conn.close()
            return self.json_response({"meeting": meeting}, status=201)

        return self.not_found("Endpoint not found")

    def handle_api_patch(self, path):
        user = self.current_user()
        if not user:
            return self.unauthorized()

        if path.startswith("/api/meetings/"):
            room_id = unquote(path.split("/api/meetings/", 1)[1])
            data = self.read_json()

            allowed_status = {"Scheduled", "Live", "Completed", "Cancelled"}
            updates = []
            values = []

            if "status" in data:
                status = data["status"]
                if status not in allowed_status:
                    return self.bad_request("Invalid meeting status")
                updates.append("status = ?")
                values.append(status)
                if status == "Completed":
                    updates.append("completed_at = ?")
                    values.append(datetime.now().isoformat(timespec="seconds"))

            if "notes" in data:
                updates.append("notes = ?")
                values.append(data.get("notes") or "")

            if not updates:
                return self.bad_request("No valid fields to update")

            conn = db()
            cur = conn.cursor()

            if user["role"] == "admin":
                values_where = [room_id]
                where = "room_id = ?"
            else:
                values_where = [room_id, user["id"]]
                where = "room_id = ? AND created_by = ?"

            cur.execute(f"UPDATE meetings SET {', '.join(updates)} WHERE {where}", values + values_where)
            conn.commit()

            if cur.rowcount == 0:
                conn.close()
                return self.not_found("Meeting not found or access denied")

            cur.execute("""
                SELECT m.*, u.name AS created_by_name
                FROM meetings m
                LEFT JOIN users u ON u.id = m.created_by
                WHERE m.room_id = ?
            """, (room_id,))
            meeting = row_to_dict(cur.fetchone())
            conn.close()
            return self.json_response({"meeting": meeting})

        return self.not_found("Endpoint not found")

    def handle_api_delete(self, path):
        user = self.current_user()
        if not user:
            return self.unauthorized()
        if user["role"] != "admin":
            return self.forbidden("Admin access required")

        if path.startswith("/api/admin/users/"):
            user_id_text = path.split("/api/admin/users/", 1)[1]
            try:
                user_id = int(user_id_text)
            except ValueError:
                return self.bad_request("Invalid user id")

            if user_id == user["id"]:
                return self.bad_request("You cannot delete your own admin account while logged in")

            conn = db()
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            deleted = cur.rowcount
            conn.close()

            if not deleted:
                return self.not_found("User not found")
            return self.json_response({"deleted": True, "user_id": user_id})

        if path.startswith("/api/meetings/"):
            room_id = unquote(path.split("/api/meetings/", 1)[1])
            conn = db()
            cur = conn.cursor()
            cur.execute("DELETE FROM meetings WHERE room_id = ?", (room_id,))
            conn.commit()
            deleted = cur.rowcount
            conn.close()
            if not deleted:
                return self.not_found("Meeting not found")
            return self.json_response({"deleted": True, "room_id": room_id})

        return self.not_found("Endpoint not found")

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    def get_token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth.replace("Bearer ", "", 1).strip()
        return None

    def current_user(self):
        token = self.get_token()
        if not token or token not in TOKENS:
            return None
        user_id = TOKENS[token]
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, role, department FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return row_to_dict(row)

    def serve_file(self, path: Path):
        if not path.exists():
            return self.not_found("File not found")
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def bad_request(self, message):
        return self.json_response({"error": message}, status=400)

    def unauthorized(self):
        return self.json_response({"error": "Unauthorized"}, status=401)

    def forbidden(self, message):
        return self.json_response({"error": message}, status=403)

    def not_found(self, message):
        return self.json_response({"error": message}, status=404)

def main():
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AppHandler)
    print(f"Reap Holding Online Meet V2 running on http://127.0.0.1:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    main()