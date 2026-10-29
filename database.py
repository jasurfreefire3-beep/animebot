import os
import json
import sqlite3
import threading
from typing import List, Optional, Dict, Any

class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.getenv("DATABASE_PATH", "anime_bot.db")
        self.db_path = db_path

        # Agar papka ko'rsatilgan bo'lsa (masalan /data/anime_bot.db), uni yaratamiz
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._lock = threading.Lock()
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Anime jadvali
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS animes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                genres TEXT NOT NULL,
                media_type TEXT NOT NULL, -- 'video' yoki 'photo'
                media_file_id TEXT NOT NULL,
                year INTEGER DEFAULT 2024,
                duration_per_ep TEXT DEFAULT '24 daq.',
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Epizodlar jadvali
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER NOT NULL,
                episode_number INTEGER NOT NULL,
                video_file_id TEXT NOT NULL,
                caption TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(anime_id, episode_number),
                FOREIGN KEY(anime_id) REFERENCES animes(id) ON DELETE CASCADE
            );
            """)

            # Foydalanuvchilar jadvali
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Tizim sozlamalari va keshlar jadvali
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)

            # Foydalanuvchilarning oxirgi xabarlarini saqlash jadvali (bitta anime ochiq turishi uchun)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                last_msg_id INTEGER
            );
            """)

            conn.commit()
            conn.close()

        self.export_to_json()

    # --- Sozlamalar metodlari ---
    def get_setting(self, key: str) -> Optional[str]:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None

    def set_setting(self, key: str, value: str):
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """, (key, value))
            conn.commit()
            conn.close()

    # --- User metodlari ---
    def register_user(self, user_id: int, username: Optional[str], first_name: Optional[str]):
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?);
            """, (user_id, username, first_name))
            conn.commit()
            conn.close()

    def get_users_count(self) -> int:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users;")
            count = cursor.fetchone()[0]
            conn.close()
            return count

    def get_user_last_msg(self, user_id: int) -> Optional[int]:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT last_msg_id FROM user_sessions WHERE user_id = ?;", (user_id,))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None

    def set_user_last_msg(self, user_id: int, message_id: int):
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO user_sessions (user_id, last_msg_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_msg_id = excluded.last_msg_id;
            """, (user_id, message_id))
            conn.commit()
            conn.close()

    # --- Anime metodlari ---
    def add_anime(self, title: str, genres: str, media_type: str, media_file_id: str, year: int = 2024, duration: str = "24 daq.") -> int:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO animes (title, genres, media_type, media_file_id, year, duration_per_ep)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (title, genres, media_type, media_file_id, year, duration))
            anime_id = cursor.lastrowid
            conn.commit()
            conn.close()
        self.export_to_json()
        return anime_id

    def get_anime(self, anime_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM animes WHERE id = ?;", (anime_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
            return None

    def update_anime_field(self, anime_id: int, field: str, value: Any):
        allowed_fields = {"title", "genres", "year", "duration_per_ep", "media_type", "media_file_id"}
        if field not in allowed_fields:
            return
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"UPDATE animes SET {field} = ? WHERE id = ?;", (value, anime_id))
            conn.commit()
            conn.close()
        self.export_to_json()

    def get_all_animes(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM animes ORDER BY id DESC;")
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def search_animes(self, query: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            pattern = f"%{query.strip()}%"
            cursor.execute("SELECT * FROM animes WHERE title LIKE ? OR genres LIKE ? ORDER BY id DESC;", (pattern, pattern))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def increment_views(self, anime_id: int):
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE animes SET views = views + 1 WHERE id = ?;", (anime_id,))
            conn.commit()
            conn.close()

    def delete_anime(self, anime_id: int):
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM episodes WHERE anime_id = ?;", (anime_id,))
            cursor.execute("DELETE FROM animes WHERE id = ?;", (anime_id,))
            conn.commit()
            conn.close()
        self.export_to_json()

    # --- Epizod metodlari ---
    def add_or_update_episode(self, anime_id: int, episode_number: int, video_file_id: str, caption: str = ""):
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO episodes (anime_id, episode_number, video_file_id, caption)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(anime_id, episode_number) DO UPDATE SET
                video_file_id = excluded.video_file_id,
                caption = excluded.caption;
            """, (anime_id, episode_number, video_file_id, caption))
            conn.commit()
            conn.close()
        self.export_to_json()

    def get_episodes(self, anime_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM episodes WHERE anime_id = ? ORDER BY episode_number ASC;
            """, (anime_id,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_episode(self, anime_id: int, episode_number: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM episodes WHERE anime_id = ? AND episode_number = ?;
            """, (anime_id, episode_number))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
            return None

    def get_episode_count(self, anime_id: int) -> int:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM episodes WHERE anime_id = ?;", (anime_id,))
            count = cursor.fetchone()[0]
            conn.close()
            return count

    def get_max_episode_number(self, anime_id: int) -> int:
        with self._lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(episode_number) FROM episodes WHERE anime_id = ?;", (anime_id,))
            res = cursor.fetchone()[0]
            conn.close()
            return res if res is not None else 0

    def export_to_json(self, json_path: str = "data/animes.json"):
        """Barcha anime va epizodlar ma'lumotlarini JSON formatda faylga saqlab borish"""
        try:
            full_path = os.path.join(os.path.dirname(__file__), json_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            animes = self.get_all_animes()
            data = []
            for a in animes:
                anime_dict = dict(a)
                anime_dict["episodes"] = self.get_episodes(a["id"])
                data.append(anime_dict)
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
