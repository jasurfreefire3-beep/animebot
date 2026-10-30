import os
import json
import sqlite3
import threading
import queue
import time
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
    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        if db_path is None:
            default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anime_bot.db")
            db_path = os.getenv("DATABASE_PATH", default_path)
        self.db_path = db_path

        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._lock = threading.RLock()

        # --- Tezkor RAM keshlar (0.0001 soniyada javob berish uchun) ---
        self._animes_cache: Dict[int, Dict[str, Any]] = {}
        self._episodes_cache: Dict[int, List[Dict[str, Any]]] = {}
        self._user_sessions_cache: Dict[int, int] = {}
        self._settings_cache: Dict[str, str] = {}
        self._users_count_cache: int = 0

        # --- Asinxron PostgreSQL fon navbati ---
        self._pg_queue = queue.Queue()
        self._pg_conn = None

        # Bazalarni ishga tushirish
        self.init_sqlite()
        self._load_cache_from_sqlite()

        # PostgreSQL fon xizmatchisini ishga tushirish
        self._bg_thread = threading.Thread(target=self._pg_worker, daemon=True, name="PGWorker")
        self._bg_thread.start()

        # Dastlabki sinxronlashni navbatga qo'yish
        self._pg_queue.put(("init_pg", ()))

        self._initialized = True

    # ==========================================
    # PostgreSQL Connection & Worker Thread
    # ==========================================
    def _get_pg_conn(self):
        """Doimiy PostgreSQL ulanishini saqlash va uzilsa qayta ulash"""
        if not HAS_PSYCOPG2:
            return None
        pg_pwd = os.getenv("PG_PASSWORD", "")
        if not pg_pwd:
            return None

        if self._pg_conn is not None:
            try:
                # Ulanish tirikligini tekshiramiz
                with self._pg_conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                return self._pg_conn
            except Exception:
                try:
                    self._pg_conn.close()
                except Exception:
                    pass
                self._pg_conn = None

        try:
            self._pg_conn = psycopg2.connect(
                host=os.getenv("PG_HOST", "psql.fr-roub1.bengt.wasmernet.com"),
                port=int(os.getenv("PG_PORT", "20184")),
                dbname=os.getenv("PG_DATABASE", "Animemuzbot"),
                user=os.getenv("PG_USER", "user_cb15d3b5"),
                password=pg_pwd,
                sslmode="require",
                connect_timeout=6
            )
            self._pg_conn.autocommit = True
            return self._pg_conn
        except Exception as e:
            return None

    def _pg_worker(self):
        """PostgreSQL ga ma'lumotlarni fonda kechikishsiz yozuvchi xizmatchi"""
        while True:
            try:
                action, args = self._pg_queue.get()
                conn = self._get_pg_conn()
                if not conn:
                    time.sleep(2)
                    self._pg_queue.put((action, args))
                    self._pg_queue.task_done()
                    continue

                with conn.cursor() as cur:
                    if action == "init_pg":
                        self._do_init_pg(cur)
                    elif action == "sync_anime":
                        anime_id, title, genres, media_type, media_file_id, year, duration, views = args
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
                        """, (anime_id, title, genres, media_type, media_file_id, year, duration, views))
                        cur.execute("SELECT setval('animes_id_seq', (SELECT COALESCE(MAX(id), 1) FROM animes));")
                    elif action == "sync_views":
                        anime_id = args[0]
                        cur.execute("UPDATE animes SET views = views + 1 WHERE id = %s;", (anime_id,))
                    elif action == "sync_field":
                        anime_id, field, value = args
                        cur.execute(f"UPDATE animes SET {field} = %s WHERE id = %s;", (value, anime_id))
                    elif action == "delete_anime":
                        anime_id = args[0]
                        cur.execute("DELETE FROM episodes WHERE anime_id = %s;", (anime_id,))
                        cur.execute("DELETE FROM animes WHERE id = %s;", (anime_id,))
                        cur.execute("DELETE FROM animes_json WHERE anime_id = %s;", (anime_id,))
                    elif action == "sync_episode":
                        anime_id, ep_num, video_id, caption = args
                        cur.execute("""
                        INSERT INTO episodes (anime_id, episode_number, video_file_id, caption)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT(anime_id, episode_number) DO UPDATE SET
                            video_file_id = EXCLUDED.video_file_id,
                            caption = EXCLUDED.caption;
                        """, (anime_id, ep_num, video_id, caption))
                        cur.execute("SELECT setval('episodes_id_seq', (SELECT COALESCE(MAX(id), 1) FROM episodes));")
                    elif action == "sync_user":
                        uid, uname, fname = args
                        cur.execute("""
                        INSERT INTO users (user_id, username, first_name)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET
                            username = EXCLUDED.username,
                            first_name = EXCLUDED.first_name;
                        """, (uid, uname, fname))
                    elif action == "sync_session":
                        uid, msg_id = args
                        cur.execute("""
                        INSERT INTO user_sessions (user_id, last_msg_id) VALUES (%s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET last_msg_id = EXCLUDED.last_msg_id;
                        """, (uid, msg_id))
                    elif action == "sync_setting":
                        key, val = args
                        cur.execute("""
                        INSERT INTO settings (key, value) VALUES (%s, %s)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
                        """, (key, val))
                    elif action == "export_json":
                        data_list = args[0]
                        for item in data_list:
                            cur.execute("""
                            INSERT INTO animes_json (anime_id, title, data, updated_at)
                            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (anime_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                data = EXCLUDED.data,
                                updated_at = CURRENT_TIMESTAMP;
                            """, (item["id"], item["title"], json.dumps(item, ensure_ascii=False)))

                self._pg_queue.task_done()
            except Exception as e:
                try:
                    self._pg_queue.task_done()
                except Exception:
                    pass
                time.sleep(0.5)

    def _do_init_pg(self, cur):
        """PostgreSQL jadvallarini tekshirish va SQLite bilan birlashtirish"""
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
        CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            anime_id INT NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
            episode_number INT NOT NULL,
            video_file_id TEXT NOT NULL,
            caption TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(anime_id, episode_number)
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS user_sessions (
            user_id BIGINT PRIMARY KEY,
            last_msg_id BIGINT
        );
        CREATE TABLE IF NOT EXISTS animes_json (
            id SERIAL PRIMARY KEY,
            anime_id INT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Agar PostgreSQL da animelar bo'lsa, ularni keshmizga yuklaymiz
        cur.execute("SELECT * FROM animes ORDER BY id DESC;")
        colnames = [desc[0] for desc in cur.description]
        pg_animes = [dict(zip(colnames, row)) for row in cur.fetchall()]

        if pg_animes:
            with self._lock:
                for a in pg_animes:
                    aid = a["id"]
                    self._animes_cache[aid] = a
                    cur.execute("SELECT * FROM episodes WHERE anime_id = %s ORDER BY episode_number ASC;", (aid,))
                    ep_cols = [desc[0] for desc in cur.description]
                    self._episodes_cache[aid] = [dict(zip(ep_cols, row)) for row in cur.fetchall()]
        else:
            # Agar PostgreSQL bo'sh bo'lsa, SQLite keshi orqali PostgreSQL ga yuklaymiz
            with self._lock:
                for a in self._animes_cache.values():
                    aid = a["id"]
                    cur.execute("""
                    INSERT INTO animes (id, title, genres, media_type, media_file_id, year, duration_per_ep, views)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                    """, (aid, a["title"], a["genres"], a.get("media_type", "photo"), a["media_file_id"], a.get("year", 2024), a.get("duration_per_ep", "24 daq."), a.get("views", 0)))
                    for ep in self._episodes_cache.get(aid, []):
                        cur.execute("""
                        INSERT INTO episodes (anime_id, episode_number, video_file_id, caption)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (anime_id, episode_number) DO NOTHING;
                        """, (aid, ep["episode_number"], ep["video_file_id"], ep.get("caption", "")))
            cur.execute("SELECT setval('animes_id_seq', (SELECT COALESCE(MAX(id), 1) FROM animes));")
            cur.execute("SELECT setval('episodes_id_seq', (SELECT COALESCE(MAX(id), 1) FROM episodes));")

    # ==========================================
    # SQLite Backup Connection & Cache Loading
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

    def _load_cache_from_sqlite(self):
        """Ishga tushganda SQLite dan barcha ma'lumotlarni RAM ga yuklab olish (0ms kechikish uchun)"""
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()

            # Animelar
            cursor.execute("SELECT * FROM animes ORDER BY id DESC;")
            rows = cursor.fetchall()
            for r in rows:
                d = dict(r)
                self._animes_cache[d["id"]] = d

            # Epizodlar
            cursor.execute("SELECT * FROM episodes ORDER BY episode_number ASC;")
            ep_rows = cursor.fetchall()
            for ep in ep_rows:
                ep_dict = dict(ep)
                aid = ep_dict["anime_id"]
                if aid not in self._episodes_cache:
                    self._episodes_cache[aid] = []
                self._episodes_cache[aid].append(ep_dict)

            # User sessions
            cursor.execute("SELECT * FROM user_sessions;")
            for s in cursor.fetchall():
                self._user_sessions_cache[s["user_id"]] = s["last_msg_id"]

            # Settings
            cursor.execute("SELECT * FROM settings;")
            for st in cursor.fetchall():
                self._settings_cache[st["key"]] = st["value"]

            # Users count
            cursor.execute("SELECT COUNT(*) FROM users;")
            self._users_count_cache = cursor.fetchone()[0]

            conn.close()

        # Agar baza yangi bo'lsa va animes.json bo'lsa, import qilamiz
        if not self._animes_cache:
            json_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "animes.json")
            if os.path.exists(json_file):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                    for item in saved:
                        aid = self.add_anime(
                            title=item["title"],
                            genres=item["genres"],
                            media_type=item.get("media_type", "photo"),
                            media_file_id=item["media_file_id"],
                            year=item.get("year", 2024),
                            duration=item.get("duration_per_ep", "24 daq.")
                        )
                        for ep in item.get("episodes", []):
                            self.add_or_update_episode(
                                anime_id=aid,
                                episode_number=ep["episode_number"],
                                video_file_id=ep["video_file_id"],
                                caption=ep.get("caption", "")
                            )
                except Exception:
                    pass

    # ==========================================
    # Settings Metodlari (0ms RAM javob)
    # ==========================================
    def get_setting(self, key: str) -> Optional[str]:
        return self._settings_cache.get(key)

    def set_setting(self, key: str, value: str):
        self._settings_cache[key] = value
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """, (key, value))
            conn.commit()
            conn.close()
        self._pg_queue.put(("sync_setting", (key, value)))

    # ==========================================
    # Users Metodlari (0ms RAM javob)
    # ==========================================
    def register_user(self, user_id: int, username: Optional[str], first_name: Optional[str]):
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?);
            """, (user_id, username, first_name))
            if cursor.rowcount > 0:
                self._users_count_cache += 1
            conn.commit()
            conn.close()
        self._pg_queue.put(("sync_user", (user_id, username, first_name)))

    def get_users_count(self) -> int:
        return self._users_count_cache

    # ==========================================
    # User Sessions Metodlari (0ms RAM javob)
    # ==========================================
    def get_user_last_msg(self, user_id: int) -> Optional[int]:
        return self._user_sessions_cache.get(user_id)

    def set_user_last_msg(self, user_id: int, message_id: int):
        self._user_sessions_cache[user_id] = message_id
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO user_sessions (user_id, last_msg_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_msg_id = excluded.last_msg_id;
            """, (user_id, message_id))
            conn.commit()
            conn.close()
        self._pg_queue.put(("sync_session", (user_id, message_id)))

    # ==========================================
    # Anime Metodlari (0ms RAM javob)
    # ==========================================
    def add_anime(self, title: str, genres: str, media_type: str, media_file_id: str, year: int = 2024, duration: str = "24 daq.") -> int:
        with self._lock:
            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO animes (title, genres, media_type, media_file_id, year, duration_per_ep)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (title, genres, media_type, media_file_id, year, duration))
            anime_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # RAM keshni darhol yangilash
            new_anime = {
                "id": anime_id,
                "title": title,
                "genres": genres,
                "media_type": media_type,
                "media_file_id": media_file_id,
                "year": year,
                "duration_per_ep": duration,
                "views": 0
            }
            self._animes_cache[anime_id] = new_anime
            self._episodes_cache[anime_id] = []

        self._pg_queue.put(("sync_anime", (anime_id, title, genres, media_type, media_file_id, year, duration, 0)))
        self.export_to_json()
        return anime_id

    def get_anime(self, anime_id: int) -> Optional[Dict[str, Any]]:
        """RAM keshdan 0.0001 soniyada animeni olish"""
        return self._animes_cache.get(anime_id)

    def update_anime_field(self, anime_id: int, field: str, value: Any):
        allowed_fields = {"title", "genres", "year", "duration_per_ep", "media_type", "media_file_id"}
        if field not in allowed_fields:
            return

        with self._lock:
            if anime_id in self._animes_cache:
                self._animes_cache[anime_id][field] = value

            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute(f"UPDATE animes SET {field} = ? WHERE id = ?;", (value, anime_id))
            conn.commit()
            conn.close()

        self._pg_queue.put(("sync_field", (anime_id, field, value)))
        self.export_to_json()

    def get_all_animes(self) -> List[Dict[str, Any]]:
        """Barcha animelarni RAM keshdan 0.0001 soniyada olish"""
        return sorted(list(self._animes_cache.values()), key=lambda x: x["id"], reverse=True)

    def search_animes(self, query: str) -> List[Dict[str, Any]]:
        """Tezkor RAM qidiruv (har qanday so'rov bo'yicha 0ms)"""
        q = query.strip().lower()
        results = []
        for a in self._animes_cache.values():
            if q in a["title"].lower() or q in a.get("genres", "").lower():
                results.append(a)
        return sorted(results, key=lambda x: x["id"], reverse=True)

    def increment_views(self, anime_id: int):
        """Ko'rishlar sonini RAM va bazada zudlik bilan oshirish"""
        with self._lock:
            if anime_id in self._animes_cache:
                self._animes_cache[anime_id]["views"] = self._animes_cache[anime_id].get("views", 0) + 1

            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("UPDATE animes SET views = views + 1 WHERE id = ?;", (anime_id,))
            conn.commit()
            conn.close()

        self._pg_queue.put(("sync_views", (anime_id,)))

    def delete_anime(self, anime_id: int):
        with self._lock:
            self._animes_cache.pop(anime_id, None)
            self._episodes_cache.pop(anime_id, None)

            conn = self.get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM episodes WHERE anime_id = ?;", (anime_id,))
            cursor.execute("DELETE FROM animes WHERE id = ?;", (anime_id,))
            conn.commit()
            conn.close()

        self._pg_queue.put(("delete_anime", (anime_id,)))
        self.export_to_json()

    # ==========================================
    # Epizod Metodlari (0ms RAM javob)
    # ==========================================
    def add_or_update_episode(self, anime_id: int, episode_number: int, video_file_id: str, caption: str = ""):
        with self._lock:
            # RAM keshni yangilash
            if anime_id not in self._episodes_cache:
                self._episodes_cache[anime_id] = []

            existing = False
            for ep in self._episodes_cache[anime_id]:
                if ep["episode_number"] == episode_number:
                    ep["video_file_id"] = video_file_id
                    ep["caption"] = caption
                    existing = True
                    break
            if not existing:
                self._episodes_cache[anime_id].append({
                    "anime_id": anime_id,
                    "episode_number": episode_number,
                    "video_file_id": video_file_id,
                    "caption": caption
                })
                self._episodes_cache[anime_id].sort(key=lambda x: x["episode_number"])

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

        self._pg_queue.put(("sync_episode", (anime_id, episode_number, video_file_id, caption)))
        self.export_to_json()

    def get_episodes(self, anime_id: int) -> List[Dict[str, Any]]:
        """Epizodlar ro'yxatini RAM keshdan darhol olish"""
        return self._episodes_cache.get(anime_id, [])

    def get_episode(self, anime_id: int, episode_number: int) -> Optional[Dict[str, Any]]:
        """Muayyan epizodni RAM keshdan darhol olish"""
        for ep in self._episodes_cache.get(anime_id, []):
            if ep["episode_number"] == episode_number:
                return ep
        return None

    def get_episode_count(self, anime_id: int) -> int:
        """Qismlar sonini RAM keshdan darhol olish"""
        return len(self._episodes_cache.get(anime_id, []))

    def get_max_episode_number(self, anime_id: int) -> int:
        eps = self._episodes_cache.get(anime_id, [])
        return max([e["episode_number"] for e in eps]) if eps else 0

    # ==========================================
    # JSON Export & PostgreSQL Sync
    # ==========================================
    def export_to_json(self, json_path: str = "data/animes.json"):
        """Barcha ma'lumotlarni faylga va PostgreSQL animes_json ga fonda saqlash"""
        try:
            full_path = os.path.join(os.path.dirname(__file__), json_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            animes = self.get_all_animes()
            data = []
            for a in animes:
                anime_dict = dict(a)
                if "created_at" in anime_dict and not isinstance(anime_dict["created_at"], str):
                    anime_dict["created_at"] = str(anime_dict["created_at"])
                anime_dict["episodes"] = self.get_episodes(a["id"])
                for ep in anime_dict["episodes"]:
                    if "created_at" in ep and not isinstance(ep["created_at"], str):
                        ep["created_at"] = str(ep["created_at"])
                data.append(anime_dict)

            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._pg_queue.put(("export_json", (data,)))
        except Exception:
            pass
