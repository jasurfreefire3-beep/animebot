import os
import time
from typing import Tuple, Optional
from aiogram import Bot
from aiogram.types import FSInputFile
from config import ADMIN_IDS
from database import Database

db = Database()
BANNER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "baner.png")

class WatchersTracker:
    def __init__(self):
        # {anime_id: {user_id: {"name": str, "timestamp": float}}}
        self._watchers = {}

    def add_watcher(self, anime_id: int, user_id: int, user_name: str):
        now = time.time()
        if anime_id not in self._watchers:
            self._watchers[anime_id] = {}
        self._watchers[anime_id][user_id] = {"name": user_name, "timestamp": now}
        self.cleanup(anime_id)

    def cleanup(self, anime_id: int):
        now = time.time()
        timeout = 15 * 60  # Oxirgi 15 daqiqa ichida faol bo'lganlar
        if anime_id in self._watchers:
            self._watchers[anime_id] = {
                uid: data for uid, data in self._watchers[anime_id].items()
                if now - data["timestamp"] < timeout
            }

    def get_watchers_info(self, anime_id: int, current_user_name: str = "Foydalanuvchi") -> Tuple[int, str]:
        self.cleanup(anime_id)
        users = self._watchers.get(anime_id, {})
        count = len(users)
        if count == 0:
            return 1, current_user_name

        names = [data["name"] for data in users.values()]
        if count <= 3:
            names_str = ", ".join(names)
        else:
            names_str = ", ".join(names[:2]) + f" va yana {count - 2} kishi"

        return count, names_str

watchers_tracker = WatchersTracker()

# --- Tezkor Cover Kesh Tizimi ---
_cached_banner_file_id: Optional[str] = None

async def get_fast_banner_cover(bot: Bot, chat_id: Optional[int] = None):
    """
    Videolarga cover qilib qo'yish uchun baner.png ning Telegram file_id sini oladi.
    Bir marta keshlab olinadi va har bir bosishda fayl qayta yuklanmasdan 0.05 soniyada uzatiladi!
    """
    global _cached_banner_file_id
    if _cached_banner_file_id:
        return _cached_banner_file_id

    # 1. Bazadan qidirish
    db_id = db.get_setting("banner_file_id")
    if db_id:
        _cached_banner_file_id = db_id
        return _cached_banner_file_id

    # 2. Agar bazada bo'lmasa, faylni adminga yoki joriy chatga yuborib file_id sini olamiz
    if os.path.exists(BANNER_PATH):
        target_chat_ids = []
        if chat_id:
            target_chat_ids.append(chat_id)
        if ADMIN_IDS:
            target_chat_ids.extend(ADMIN_IDS)
        target_chat_ids.append(8278030347)

        for cid in target_chat_ids:
            try:
                msg = await bot.send_photo(
                    chat_id=cid,
                    photo=FSInputFile(BANNER_PATH),
                    caption="⚙️ Tizim: Baner muqovasi tezkor keshga yuklandi"
                )
                _cached_banner_file_id = msg.photo[-1].file_id
                db.set_setting("banner_file_id", _cached_banner_file_id)
                try:
                    await msg.delete()
                except Exception:
                    pass
                return _cached_banner_file_id
            except Exception:
                continue

        # Agar yuborish imkoni bo'lmasa, vaqtinchalik FSInputFile qaytaramiz
        return FSInputFile(BANNER_PATH)

    return None
