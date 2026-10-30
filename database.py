import os
import json
import sqlite3
import threading
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anime_bot.db")
            db_path = os.getenv("DATABASE_PATH", default_path)
        self.db_path = db_path

        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._lock = threading.Lock()
        self.init_sqlite()
        self.init_pg()

    # ==========================================
    # PostgreSQL Connection & Init
    # ==========================================
    def get_pg_connection(self):
        """PostgreSQL ulanishini olish"""
        if not HAS_PSYCOPG2:
            return None
        pg_pwd = os.getenv("PG_PASSWORD", "")
        if not pg_pwd:
            return None
        try:
            return psycopg2.connect(
                host=os.getenv("PG_HOST", "psql.fr-roub1.bengt.wasmernet.com"),
                port=int(os.getenv("PG_PORT", "20184")),
                dbname=os.getenv("PG_DATABASE", "Animemuzbot"),
                user=os.getenv("PG_USER", "user_cb15d3b5"),
                password=pg_pwd,
                sslmode="require",
                connect_timeout=5
            )
        except Exception:
            return None

    def init_pg(self):
        """PostgreSQL ma'lumotlar bazasida barcha jadvallarni ochish va sinxronlash"""
        conn = self.get_pg_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                # 1. Animelar jadvali
                cur.execute("""
                CREATE TABLE IF NOT EXISTS animes (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    genres TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT 'photo',
                    media_file_id TEXT NOT NULL,
                    year INT DEFAULT 2024,
                    duration_per_ep TEXT DEFAULT '24 daq.',
                    views INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 2. Epizodlar jadvali
                cur.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id SERIAL PRIMARY KEY,
                    anime_id INT NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
                    episode_number INT NOT NULL,
                    video_file_id TEXT NOT NULL,
                    caption TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(anime_id, episode_number)
                );
                """)

                # 3. Foydalanuvchilar jadvali
                cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 4. Tizim sozlamalari
                cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """)

                # 5. Foydalanuvchi sessiyalari
                cur.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id BIGINT PRIMARY KEY,
                    last_msg_id BIGINT
                );
                """)

                # 6. JSON formatdagi to'liq animelar jadvali
                cur.execute("""
                CREATE TABLE IF NOT EXISTS animes_json (
                    id SERIAL PRIMARY KEY,
                    anime_id INT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

            conn.commit()

            # Agar PostgreSQL yangi yoki bo'sh bo'lsa, mavjud ma'lumotlarni SQLite / animes.json dan yuklaymiz
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM animes;")
                pg_count = cur.fetchone()[0]

            if pg_count == 0:
                sq_animes = self._sqlite_get_all_animes()
                if sq_animes:
                    with conn.cursor() as cur:
                        for a in sq_animes:
                            cur.execute("""
                            INSERT INTO animes (id, title, genres, media_type, media_file_id, year, duration_per_ep, views)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                title = EXCLUDED.title,
                                genres = EXCLUDED.genres,
                                media_type = EXCLUDED.media_type,
                                media_file_id = EXCLUDED.media_file_id,
                                year = EXCLUDED.year,
                                duration_per_ep = EXCLUDED.duration_per_ep,
                                views = EXCLUDED.views;
                            """, (a["id"], a["title"], a["genres"], a.get("media_type", "photo"), a["media_file_id"], a.get("year", 2024), a.get("duration_per_ep", "24 daq."), a.get("views", 0)))
                            cur.execute("SELECT setval('animes_id_seq', (SELECT COALESCE(MAX(id), 1) FROM animes));")

                            for ep in self._sqlite_get_episodes(a["id"]):
                                cur.execute("""
                                INSERT INTO episodes (anime_id, episode_number, video_file_id, caption)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (anime_id, episode_number) DO UPDATE SET
                                    video_file_id = EXCLUDED.video_file_id,
                                    caption = EXCLUDED.caption;
                                """, (a["id"], ep["episode_number"], ep["video_file_id"], ep.get("caption", "")))
                            cur.execute("SELECT setval('episodes_id_seq', (SELECT COALESCE(MAX(id), 1) FROM episodes));")
                    conn.commit()

            conn.close()
            print("✅ PostgreSQL ma'lumotlar bazasiga muvaffaqiyatli ulandi va barcha jadvallar faollashtirildi!")
            self.export_to_json()
        except Exception as e:
            print(f"⚠️ PostgreSQL init xatosi: {e}")

    # ==========================================
    # SQLite Backup Connection & Init
    # ==========================================
    def get_sqlite_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_sqlite(self):
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS animes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                genres TEXT NOT NULL,
                media_type TEXT NOT NULL DEFAULT 'photo',
                media_file_id TEXT NOT NULL,
                year INTEGER DEFAULT 2024,
                duration_per_ep TEXT DEFAULT '24 daq.',
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
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
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                last_msg_id INTEGER
            );
            """)
            conn.commit()
            conn.close()

    # ==========================================
    # Settings Metodlari
    # ==========================================
    def get_setting(self, key: str) -> Optional[str]:
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT value FROM settings WHERE key = %s;", (key,))
                    row = cur.fetchone()
                    pg_conn.close()
                    if row:
                        return row[0]
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None

    def set_setting(self, key: str, value: str):
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO settings (key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
                    """, (key, value))
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """, (key, value))
            conn.commit()
            conn.close()

    # ==========================================
    # Users Metodlari
    # ==========================================
    def register_user(self, user_id: int, username: Optional[str], first_name: Optional[str]):
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO users (user_id, username, first_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name;
                    """, (user_id, username, first_name))
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?);
            """, (user_id, username, first_name))
            conn.commit()
            conn.close()

    def get_users_count(self) -> int:
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM users;")
                    cnt = cur.fetchone()[0]
                    pg_conn.close()
                    return cnt
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users;")
            cnt = cursor.fetchone()[0]
            conn.close()
            return cnt

    # ==========================================
    # User Sessions Metodlari
    # ==========================================
    def get_user_last_msg(self, user_id: int) -> Optional[int]:
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT last_msg_id FROM user_sessions WHERE user_id = %s;", (user_id,))
                    row = cur.fetchone()
                    pg_conn.close()
                    if row:
                        return row[0]
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT last_msg_id FROM user_sessions WHERE user_id = ?;", (user_id,))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None

    def set_user_last_msg(self, user_id: int, message_id: int):
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO user_sessions (user_id, last_msg_id) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET last_msg_id = EXCLUDED.last_msg_id;
                    """, (user_id, message_id))
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO user_sessions (user_id, last_msg_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_msg_id = excluded.last_msg_id;
            """, (user_id, message_id))
            conn.commit()
            conn.close()

    # ==========================================
    # Anime Metodlari
    # ==========================================
    def add_anime(self, title: str, genres: str, media_type: str, media_file_id: str, year: int = 2024, duration: str = "24 daq.") -> int:
        anime_id = None
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO animes (title, genres, media_type, media_file_id, year, duration_per_ep)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """, (title, genres, media_type, media_file_id, year, duration))
                    anime_id = cur.fetchone()[0]
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            if anime_id:
                cursor.execute("""
                INSERT OR REPLACE INTO animes (id, title, genres, media_type, media_file_id, year, duration_per_ep)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (anime_id, title, genres, media_type, media_file_id, year, duration))
            else:
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
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM animes WHERE id = %s;", (anime_id,))
                    row = cur.fetchone()
                    pg_conn.close()
                    if row:
                        return dict(row)
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
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

        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute(f"UPDATE animes SET {field} = %s WHERE id = %s;", (value, anime_id))
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute(f"UPDATE animes SET {field} = ? WHERE id = ?;", (value, anime_id))
            conn.commit()
            conn.close()

        self.export_to_json()

    def get_all_animes(self) -> List[Dict[str, Any]]:
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM animes ORDER BY id DESC;")
                    rows = cur.fetchall()
                    pg_conn.close()
                    return [dict(r) for r in rows]
            except Exception:
                pass

        return self._sqlite_get_all_animes()

    def _sqlite_get_all_animes(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM animes ORDER BY id DESC;")
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def search_animes(self, query: str) -> List[Dict[str, Any]]:
        pattern = f"%{query.strip()}%"
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                    SELECT * FROM animes
                    WHERE title ILIKE %s OR genres ILIKE %s
                    ORDER BY id DESC;
                    """, (pattern, pattern))
                    rows = cur.fetchall()
                    pg_conn.close()
                    return [dict(r) for r in rows]
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM animes WHERE title LIKE ? OR genres LIKE ? ORDER BY id DESC;", (pattern, pattern))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def increment_views(self, anime_id: int):
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("UPDATE animes SET views = views + 1 WHERE id = %s;", (anime_id,))
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("UPDATE animes SET views = views + 1 WHERE id = ?;", (anime_id,))
            conn.commit()
            conn.close()

    def delete_anime(self, anime_id: int):
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("DELETE FROM episodes WHERE anime_id = %s;", (anime_id,))
                    cur.execute("DELETE FROM animes WHERE id = %s;", (anime_id,))
                    cur.execute("DELETE FROM animes_json WHERE anime_id = %s;", (anime_id,))
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM episodes WHERE anime_id = ?;", (anime_id,))
            cursor.execute("DELETE FROM animes WHERE id = ?;", (anime_id,))
            conn.commit()
            conn.close()

        self.export_to_json()

    # ==========================================
    # Epizod Metodlari
    # ==========================================
    def add_or_update_episode(self, anime_id: int, episode_number: int, video_file_id: str, caption: str = ""):
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO episodes (anime_id, episode_number, video_file_id, caption)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(anime_id, episode_number) DO UPDATE SET
                        video_file_id = EXCLUDED.video_file_id,
                        caption = EXCLUDED.caption;
                    """, (anime_id, episode_number, video_file_id, caption))
                pg_conn.commit()
                pg_conn.close()
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
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
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM episodes WHERE anime_id = %s ORDER BY episode_number ASC;", (anime_id,))
                    rows = cur.fetchall()
                    pg_conn.close()
                    return [dict(r) for r in rows]
            except Exception:
                pass

        return self._sqlite_get_episodes(anime_id)

    def _sqlite_get_episodes(self, anime_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes WHERE anime_id = ? ORDER BY episode_number ASC;", (anime_id,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_episode(self, anime_id: int, episode_number: int) -> Optional[Dict[str, Any]]:
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM episodes WHERE anime_id = %s AND episode_number = %s;", (anime_id, episode_number))
                    row = cur.fetchone()
                    pg_conn.close()
                    if row:
                        return dict(row)
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes WHERE anime_id = ? AND episode_number = ?;", (anime_id, episode_number))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
            return None

    def get_episode_count(self, anime_id: int) -> int:
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM episodes WHERE anime_id = %s;", (anime_id,))
                    cnt = cur.fetchone()[0]
                    pg_conn.close()
                    return cnt
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM episodes WHERE anime_id = ?;", (anime_id,))
            cnt = cursor.fetchone()[0]
            conn.close()
            return cnt

    def get_max_episode_number(self, anime_id: int) -> int:
        pg_conn = self.get_pg_connection()
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT MAX(episode_number) FROM episodes WHERE anime_id = %s;", (anime_id,))
                    res = cur.fetchone()[0]
                    pg_conn.close()
                    return res if res is not None else 0
            except Exception:
                pass

        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(episode_number) FROM episodes WHERE anime_id = ?;", (anime_id,))
            res = cursor.fetchone()[0]
            conn.close()
            return res if res is not None else 0

    # ==========================================
    # JSON Export & PostgreSQL Sync
    # ==========================================
    def export_to_json(self, json_path: str = "data/animes.json"):
        """Barcha anime va epizodlar ma'lumotlarini JSON formatda faylga va PostgreSQL animes_json jadvaliga saqlash"""
        try:
            full_path = os.path.join(os.path.dirname(__file__), json_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            animes = self.get_all_animes()
            data = []
            for a in animes:
                anime_dict = dict(a)
                # datetime obyektlarini str ga o'tkazish
                if "created_at" in anime_dict and not isinstance(anime_dict["created_at"], str):
                    anime_dict["created_at"] = str(anime_dict["created_at"])
                anime_dict["episodes"] = self.get_episodes(a["id"])
                for ep in anime_dict["episodes"]:
                    if "created_at" in ep and not isinstance(ep["created_at"], str):
                        ep["created_at"] = str(ep["created_at"])
                data.append(anime_dict)

            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # PostgreSQL dagi animes_json jadvaliga JSONB formatda to'liq saqlash
            pg_conn = self.get_pg_connection()
            if pg_conn:
                try:
                    with pg_conn.cursor() as cur:
                        for item in data:
                            cur.execute("""
                            INSERT INTO animes_json (anime_id, title, data, updated_at)
                            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (anime_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                data = EXCLUDED.data,
                                updated_at = CURRENT_TIMESTAMP;
                            """, (item["id"], item["title"], json.dumps(item, ensure_ascii=False)))
                    pg_conn.commit()
                    pg_conn.close()
                except Exception:
                    pass
        except Exception:
            pass
