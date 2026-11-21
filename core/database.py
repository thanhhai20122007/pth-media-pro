import sqlite3
import json
import os
import time
from typing import Dict, List, Optional, Any
from core.config import DB_PATH, DEFAULT_SETTINGS


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                platform TEXT DEFAULT 'general',
                title TEXT,
                author TEXT,
                thumbnail TEXT,
                raw_path TEXT,
                final_path TEXT,
                file_size INTEGER DEFAULT 0,
                duration INTEGER DEFAULT 0,
                status TEXT DEFAULT 'PENDING',
                progress REAL DEFAULT 0.0,
                speed TEXT DEFAULT '',
                format_type TEXT DEFAULT 'video',
                session_id TEXT DEFAULT 'default',
                retry_count INTEGER DEFAULT 0,
                error_log TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tự động nâng cấp cột session_id nếu đang dùng database cũ
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN session_id TEXT DEFAULT 'default'")
        except Exception:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Khởi tạo cài đặt mặc định nếu chưa có
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (k, json.dumps(v))
            )


def add_task(url: str, format_type: str = "video", title: str = None, session_id: str = "default") -> Optional[int]:
    """Thêm một link vào danh sách chờ tải với phiên người dùng độc lập"""
    with get_db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO tasks (url, format_type, title, status, progress, retry_count, session_id)
                VALUES (?, ?, ?, 'PENDING', 0.0, 0, ?)
                ON CONFLICT(url) DO UPDATE SET
                    status = 'PENDING',
                    retry_count = 0,
                    error_log = NULL,
                    format_type = excluded.format_type,
                    session_id = excluded.session_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (url.strip(), format_type, title, session_id or "default")
            )
            return cur.lastrowid
        except Exception as e:
            print(f"Lỗi thêm task: {e}")
            return None


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def get_tasks(limit: int = 50, status: Optional[str] = None, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db() as conn:
        if session_id:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE session_id = ? AND status = ? ORDER BY id DESC LIMIT ?",
                    (session_id, status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, limit)
                ).fetchall()
        else:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [dict(r) for r in rows]


def get_next_pending_task() -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE status = 'PENDING' AND retry_count < 3 ORDER BY id ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def claim_next_pending_task() -> Optional[Dict[str, Any]]:
    """
    Lấy và khóa nguyên tử (atomic claim) 1 task PENDING tiếp theo cho worker,
    ngăn chặn triệt để xung đột (race condition) khi nhiều worker chạy song song.
    """
    with get_db() as conn:
        cur = conn.execute("""
            UPDATE tasks 
            SET status = 'DOWNLOADING', 
                speed = 'Khởi động',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id FROM tasks 
                WHERE status = 'PENDING' AND retry_count < 3 
                ORDER BY id ASC LIMIT 1
            )
            RETURNING *;
        """)
        row = cur.fetchone()
        return dict(row) if row else None


def update_task(task_id: int, **kwargs):
    fields = []
    values = []
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        values.append(v)
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(task_id)

    query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"
    with get_db() as conn:
        conn.execute(query, tuple(values))


def update_task_progress(task_id: int, progress: float, speed: str = "", status: str = None):
    with get_db() as conn:
        if status:
            conn.execute(
                "UPDATE tasks SET progress = ?, speed = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (progress, speed, status, task_id)
            )
        else:
            conn.execute(
                "UPDATE tasks SET progress = ?, speed = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (progress, speed, task_id)
            )


def delete_task(task_id: int, delete_file: bool = False) -> bool:
    task = get_task(task_id)
    if not task:
        return False

    if delete_file:
        for p in (task.get("raw_path"), task.get("final_path")):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return True


def clear_completed_tasks():
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE status IN ('DONE', 'READY')")


def get_stats(session_id: Optional[str] = None) -> Dict[str, Any]:
    with get_db() as conn:
        if session_id:
            total = conn.execute("SELECT COUNT(*) FROM tasks WHERE session_id = ?", (session_id,)).fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE session_id = ? AND status IN ('DONE', 'READY')", (session_id,)).fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE session_id = ? AND status IN ('PENDING', 'DOWNLOADING', 'PROCESSING')", (session_id,)).fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM tasks WHERE session_id = ? AND status = 'FAILED'", (session_id,)).fetchone()[0]
            total_size = conn.execute("SELECT SUM(file_size) FROM tasks WHERE session_id = ? AND status IN ('DONE', 'READY')", (session_id,)).fetchone()[0] or 0
            platforms = conn.execute("SELECT platform, COUNT(*) as cnt FROM tasks WHERE session_id = ? GROUP BY platform", (session_id,)).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('DONE', 'READY')").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('PENDING', 'DOWNLOADING', 'PROCESSING')").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'FAILED'").fetchone()[0]
            total_size = conn.execute("SELECT SUM(file_size) FROM tasks WHERE status IN ('DONE', 'READY')").fetchone()[0] or 0
            platforms = conn.execute("SELECT platform, COUNT(*) as cnt FROM tasks GROUP BY platform").fetchall()

        platform_stats = {r["platform"]: r["cnt"] for r in platforms}

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "failed": failed,
            "total_size": total_size,
            "platforms": platform_stats
        }


def get_setting(key: str, default: Any = None) -> Any:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default


def set_setting(key: str, value: Any):
    val_str = json.dumps(value) if not isinstance(value, str) else value
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, val_str)
        )


def get_all_settings() -> Dict[str, Any]:
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except Exception:
                result[r["key"]] = r["value"]
        return result
