import os
import urllib.request
from typing import Optional, List, Dict, Any
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InputMediaVideo,
    InputMediaPhoto,
    FSInputFile,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedVideo,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChosenInlineResult
)
from aiogram.filters import CommandStart, CommandObject, Command

from database import Database
from keyboards import (
    get_anime_card_kb,
    get_episode_grid_kb,
    get_start_kb,
    get_anime_list_kb
)
from utils.tracker import watchers_tracker, get_fast_banner_cover

user_router = Router()
db = Database()

# --- Kesh: Telegram rasmlari URL manzillari ---
_thumb_cache: dict = {
    "AgACAgIAAxkBAAMLauNlk_o72T_Y5-dh00IUq1XBxcYAAg8iaxtZ5BhLbKnA8VRW6-YBAAMCAAN5AAM9BA": "https://files.catbox.moe/rg5kju.jpg"
}

def upload_to_catbox(file_bytes: bytes) -> Optional[str]:
    """Catbox.moe ga yuklab, Telegram inline qidiruv uchun toza HTTPS CDN rasm URL olish"""
    try:
        boundary = '----WebKitFormBoundary' + os.urandom(8).hex()
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
            f'fileupload\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="fileToUpload"; filename="thumb.jpg"\r\n'
            f'Content-Type: image/jpeg\r\n\r\n'
        ).encode('utf-8') + file_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

        req = urllib.request.Request(
            'https://catbox.moe/user/api.php',
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}', 'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            url = resp.read().decode('utf-8').strip()
            if url.startswith('http'):
                return url
    except Exception:
        pass
    return None

async def get_telegram_thumb_url(bot, file_id: str):
    """Inline qidiruvda animening haqiqiy muqova rasmini ko'rsatish uchun toza CDN URL olish"""
    if not file_id:
        return None
    if file_id in _thumb_cache:
        return _thumb_cache[file_id]

    # Bazadan tekshirish
    db_thumb = db.get_setting(f"thumb_{file_id}")
    if db_thumb:
        _thumb_cache[file_id] = db_thumb
        return db_thumb

    try:
        f = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{f.file_path}"
        req = urllib.request.Request(file_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()

        catbox_url = upload_to_catbox(data)
        if catbox_url:
            _thumb_cache[file_id] = catbox_url
            db.set_setting(f"thumb_{file_id}", catbox_url)
            return catbox_url

        _thumb_cache[file_id] = file_url
        return file_url
    except Exception:
        return None

# --- ⚡ TELEGRAM TEZKOR INLINE QIDIRUV (@Animem_uz_bot <nom>) ---
@user_router.inline_query()
async def inline_anime_search(inline_query: InlineQuery):
    query = inline_query.query.strip().lower()

    if not query:
        animes = db.get_all_animes()[:30]
    else:
        animes = db.search_animes(query)[:30]

    results = []

    for a in animes:
        anime_id = a["id"]
        ep_count = db.get_episode_count(anime_id)
        year = a.get("year", 2024)
        genres = a.get("genres", "")
        title = a["title"]
        media_type = a.get("media_type", "photo")
        media_file_id = a.get("media_file_id")

        ep_str = f"{ep_count} / {ep_count} epizod" if ep_count > 0 else "0 epizod (Tez kunda)"
        # Autostart tashlaydigan formatdagi to'liq ramkali matn
        card_text = format_anime_card_text(a, ep_count)
        # Autostart dagi xuddi o'sha yashil 'Tomosha qilish' tugmasi
        kb = get_anime_card_kb(anime_id, ep_count)

        desc = f"📅 {year}-yil • 📺 {ep_str} • 🏷️ {genres}"
        if len(desc) > 85:
            desc = desc[:82] + "..."

        thumb_url = await get_telegram_thumb_url(inline_query.bot, media_file_id)

        # Inline ro'yxatda: Rasm ham, uning yonida qalin harflar bilan Anime Nomi va yili ham chiqadi
        results.append(
            InlineQueryResultArticle(
                id=f"anime_{anime_id}",
                title=f"🎬 {title} ({year})",
                description=desc,
                thumbnail_url=thumb_url,
                thumbnail_width=100,
                thumbnail_height=100,
                input_message_content=InputTextMessageContent(
                    message_text=f"🎬 <b>{title}</b> ({year})",
                    parse_mode="HTML"
                ),
                reply_markup=kb
            )
        )

    if query and not animes:
        results.append(
            InlineQueryResultArticle(
                id="no_results",
                title=f"❌ '{query}' nomli anime topilmadi",
                description="Boshqa nom bilan qidirib ko'ring",
                input_message_content=InputTextMessageContent(
                    message_text=f"🔍 <b>'{query}'</b> bo'yicha hech qanday anime topilmadi.\n\nAnime qidirish uchun nomini to'g'ri yozing.",
                    parse_mode="HTML"
                )
            )
        )

    await inline_query.answer(results, cache_time=2, is_personal=True)

_last_chosen_anime: dict = {}

@user_router.chosen_inline_result()
async def chosen_inline_handler(chosen: ChosenInlineResult):
    """Inline qidiruvdan anime tanlanganda ko'rishlar sonini oshirish va xotiraga olish"""
    try:
        if chosen.result_id.startswith("anime_"):
            aid = int(chosen.result_id.replace("anime_", ""))
            db.increment_views(aid)
            if chosen.from_user:
                _last_chosen_anime[chosen.from_user.id] = aid
    except Exception:
        pass

# --- /search yoki /qidiruv buyrug'i ---
@user_router.message(Command("search"))
@user_router.message(Command("qidiruv"))
async def search_command_handler(message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    kb = get_start_kb()
    sent_msg = await message.answer(
        "🔍 <b>Animelarni qidirish:</b>\n\n"
        "Quyidagi tugma orqali anime nomini yozib qidirishingiz yoki to'liq ro'yxatni ochishingiz mumkin:",
        parse_mode="HTML",
        reply_markup=kb
    )
    db.set_user_last_msg(message.from_user.id, sent_msg.message_id)

def format_anime_card_text(anime: dict, ep_count: int) -> str:
    """1-rasmdagi va foydalanuvchi so'ragan ramkali (blockquote) ko'rinish"""
    views = anime.get("views", 0)
    year = anime.get("year", 2024)
    duration = anime.get("duration_per_ep", "24 daq.")
    ep_str = f"{ep_count} / {ep_count} epizod" if ep_count > 0 else "0 epizod (Tez kunda)"

    return (
        f"📕 <b>{anime['title']}</b>\n\n"
        f"<blockquote>{anime['genres']} ”</blockquote>\n"
        f"<blockquote>📺 {ep_str} ”</blockquote>\n"
        f"<blockquote>📦 {duration} • 📅 {year} ”</blockquote>\n"
        f"<blockquote>👁️ {views} marta ko'rildi ”</blockquote>"
    )

def format_episode_player_text(anime: dict, current_ep: int, ep_count: int, count: int, names_str: str) -> str:
    """2-rasmdagi va foydalanuvchi so'ragan ramkali (blockquote) ko'rinish"""
    return (
        f"📕 <b>{anime['title']}</b>\n\n"
        f"<blockquote>📺 Epizod {current_ep} / {ep_count} • 🎙️ animem.uz ”</blockquote>\n"
        f"<blockquote>🟢 Hozir tomosha qilmoqda ({count} kishi): ”\n"
        f"{names_str}</blockquote>"
    )

# --- Helper: Eski xabarni o'chirish ---
async def clean_previous_bot_message(bot, chat_id: int, user_id: int):
    """Foydalanuvchida avval ochilgan anime yoki xabarni o'chirish (faqat bitta xabar turishi uchun)"""
    old_msg_id = db.get_user_last_msg(user_id)
    if old_msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception:
            pass

# --- /start komandasi ---
@user_router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject):
    user = message.from_user
    db.register_user(user.id, user.username, user.first_name)

    # 1. Foydalanuvchi yozgan /start buyrug'ini darhol o'chirish
    try:
        await message.delete()
    except Exception:
        pass

    # 2. Tepada turgan avvalgi anime yoki bot xabarini o'chirish (faqat bitta anime qolishi uchun)
    await clean_previous_bot_message(message.bot, message.chat.id, user.id)

    args = command.args
    # Agar start argumenti orqali anime ochilayotgan bo'lsa (Auto-Start link)
    if args and args.startswith("anime_"):
        try:
            anime_id = int(args.split("_")[1])
            await send_anime_card(message, anime_id)
            return
        except (IndexError, ValueError):
            pass

    # Oddiy /start - Foydalanuvchiga faqat salomlashish va yashil qidiruv tugmasi
    text = (
        f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
        f"🎬 <b>Animem Uz</b> rasmiy anime botiga xush kelibsiz.\n"
        f"Bu yerda sevimli animelaringizni eng yuqori sifatda tomosha qilishingiz mumkin."
    )
    kb = get_start_kb()
    sent_msg = await message.answer(text, parse_mode="HTML", reply_markup=kb)
    db.set_user_last_msg(user.id, sent_msg.message_id)

async def send_anime_card(message: Message, anime_id: int, user_id: Optional[int] = None):
    if user_id is None:
        user_id = message.from_user.id if message.from_user else None

    anime = db.get_anime(anime_id)
    if not anime:
        sent_err = await message.answer("Kechirasiz, ushbu anime topilmadi yoki o'chirilgan.")
        if user_id:
            db.set_user_last_msg(user_id, sent_err.message_id)
        return

    db.increment_views(anime_id)
    anime = db.get_anime(anime_id)
    ep_count = db.get_episode_count(anime_id)
    card_text = format_anime_card_text(anime, ep_count)
    kb = get_anime_card_kb(anime_id, ep_count)

    media_type = anime.get("media_type", "photo")
    media_file_id = anime.get("media_file_id")
    chat_id = message.chat.id if message.chat else None
    cover = await get_fast_banner_cover(message.bot, chat_id=chat_id)

    sent_msg = None
    if media_type == "video":
        try:
            sent_msg = await message.answer_video(
                video=media_file_id,
                caption=card_text,
                parse_mode="HTML",
                cover=cover,
                reply_markup=kb
            )
        except Exception:
            sent_msg = await message.answer_video(
                video=media_file_id,
                caption=card_text,
                parse_mode="HTML",
                reply_markup=kb
            )
    else:
        sent_msg = await message.answer_photo(
            photo=media_file_id,
            caption=card_text,
            parse_mode="HTML",
            reply_markup=kb
        )

    if sent_msg and user_id:
        db.set_user_last_msg(user_id, sent_msg.message_id)

# --- 1-rasmdan 2-rasmga o'tish (Tomosha qilish tugmasi) ---
@user_router.callback_query(F.data.startswith("watch_"))
async def watch_anime_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    anime_id = int(parts[1])
    target_ep = int(parts[2]) if len(parts) > 2 else 1

    await play_episode(callback, anime_id, target_ep, page=1)

# --- Epizod tugmasi bosilganda (2-rasmdagi disklar) ---
@user_router.callback_query(F.data.startswith("ep_"))
async def episode_click_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    anime_id = int(parts[1])
    ep_num = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1

    await play_episode(callback, anime_id, ep_num, page)

async def play_episode(callback: CallbackQuery, anime_id: int, episode_number: int, page: int = 1):
    anime = db.get_anime(anime_id)
    if not anime:
        await callback.answer("Anime topilmadi!", show_alert=True)
        return

    ep_count = db.get_episode_count(anime_id)
    if ep_count == 0:
        await callback.answer("Ushbu anime uchun hali epizodlar yuklanmagan!", show_alert=True)
        return

    db.increment_views(anime_id)
    anime = db.get_anime(anime_id)

    # 100% haqiqiy tomoshabinlar kuzatuvi
    user = callback.from_user
    display_name = user.first_name if user and user.first_name else (f"@{user.username}" if user and user.username else "Foydalanuvchi")
    watchers_tracker.add_watcher(anime_id, user.id, display_name)
    count, names_str = watchers_tracker.get_watchers_info(anime_id, display_name)

    episodes = db.get_episodes(anime_id)
    ep_numbers = [e["episode_number"] for e in episodes]

    # Tanlangan epizodni olish (agar mavjud bo'lmasa, birinchisini olish)
    ep = db.get_episode(anime_id, episode_number)
    if not ep and episodes:
        ep = episodes[0]
        episode_number = ep["episode_number"]

    player_text = format_episode_player_text(anime, episode_number, ep_count, count, names_str)
    kb = get_episode_grid_kb(anime_id, episode_number, ep_numbers, page=page)

    chat_id = callback.message.chat.id if callback.message else None
    cover = await get_fast_banner_cover(callback.bot, chat_id=chat_id)

    # Agar video yuklangan bo'lsa, videoni jo'natish yoki tahrirlash
    if ep and ep.get("video_file_id"):
        video_id = ep["video_file_id"]
        try:
            if callback.inline_message_id:
                await callback.bot.edit_message_media(
                    inline_message_id=callback.inline_message_id,
                    media=InputMediaVideo(media=video_id, caption=player_text, parse_mode="HTML", cover=cover),
                    reply_markup=kb
                )
            elif callback.message:
                await callback.message.edit_media(
                    media=InputMediaVideo(media=video_id, caption=player_text, parse_mode="HTML", cover=cover),
                    reply_markup=kb
                )
                db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
        except Exception:
            if callback.inline_message_id:
                bot_info = await callback.bot.get_me()
                await callback.answer(url=f"https://t.me/{bot_info.username}?start=anime_{anime_id}")
                return
            # Agar edit qilib bo'lmasa, eski xabarni o'chirib, yangisini yuboramiz
            try:
                await callback.message.delete()
            except Exception:
                pass
            new_msg = None
            try:
                new_msg = await callback.message.answer_video(
                    video=video_id,
                    caption=player_text,
                    parse_mode="HTML",
                    cover=cover,
                    reply_markup=kb
                )
            except Exception:
                new_msg = await callback.message.answer_video(
                    video=video_id,
                    caption=player_text,
                    parse_mode="HTML",
                    reply_markup=kb
                )
            if new_msg:
                db.set_user_last_msg(callback.from_user.id, new_msg.message_id)
    else:
        # Agar qism videosi topilmasa, captionni yangilaymiz
        try:
            if callback.inline_message_id:
                await callback.bot.edit_message_caption(
                    inline_message_id=callback.inline_message_id,
                    caption=player_text,
                    parse_mode="HTML",
                    reply_markup=kb
                )
            elif callback.message:
                await callback.message.edit_caption(
                    caption=player_text,
                    parse_mode="HTML",
                    reply_markup=kb
                )
                db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
        except Exception:
            if callback.inline_message_id:
                bot_info = await callback.bot.get_me()
                await callback.answer(url=f"https://t.me/{bot_info.username}?start=anime_{anime_id}")
                return
            try:
                await callback.message.delete()
            except Exception:
                pass
            new_msg = await callback.message.answer(
                text=player_text,
                parse_mode="HTML",
                reply_markup=kb
            )
            if new_msg:
                db.set_user_last_msg(callback.from_user.id, new_msg.message_id)

    await callback.answer(f"{episode_number}-epizod tanlandi")

# --- Sahifalash (Pagination) ---
@user_router.callback_query(F.data.startswith("page_"))
async def page_navigate_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    anime_id = int(parts[1])
    current_ep = int(parts[2])
    page = int(parts[3])

    episodes = db.get_episodes(anime_id)
    ep_numbers = [e["episode_number"] for e in episodes]
    kb = get_episode_grid_kb(anime_id, current_ep, ep_numbers, page=page)

    try:
        if callback.inline_message_id:
            await callback.bot.edit_message_reply_markup(
                inline_message_id=callback.inline_message_id,
                reply_markup=kb
            )
        elif callback.message:
            await callback.message.edit_reply_markup(reply_markup=kb)
            db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
    except Exception:
        pass
    await callback.answer()

# --- Asosiy kartaga qaytish ---
@user_router.callback_query(F.data.startswith("card_"))
async def back_to_card_callback(callback: CallbackQuery):
    anime_id = int(callback.data.split("_")[1])
    anime = db.get_anime(anime_id)
    if not anime:
        await callback.answer("Anime topilmadi!", show_alert=True)
        return

    ep_count = db.get_episode_count(anime_id)
    card_text = format_anime_card_text(anime, ep_count)
    kb = get_anime_card_kb(anime_id, ep_count)

    media_type = anime.get("media_type", "photo")
    media_file_id = anime.get("media_file_id")
    chat_id = callback.message.chat.id if callback.message else None
    cover = await get_fast_banner_cover(callback.bot, chat_id=chat_id)

    media_obj = InputMediaVideo(media=media_file_id, caption=card_text, parse_mode="HTML", cover=cover) if media_type == "video" else InputMediaPhoto(media=media_file_id, caption=card_text, parse_mode="HTML")

    try:
        if callback.inline_message_id:
            await callback.bot.edit_message_media(
                inline_message_id=callback.inline_message_id,
                media=media_obj,
                reply_markup=kb
            )
        elif callback.message:
            await callback.message.edit_media(
                media=media_obj,
                reply_markup=kb
            )
            db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
    except Exception:
        if callback.inline_message_id:
            bot_info = await callback.bot.get_me()
            await callback.answer(url=f"https://t.me/{bot_info.username}?start=anime_{anime_id}")
            return
        # Agar edit qilib bo'lmasa, eski xabarni o'chirib, yangi yuboramiz
        try:
            await callback.message.delete()
        except Exception:
            pass

        new_msg = None
        if media_type == "video":
            try:
                new_msg = await callback.message.answer_video(
                    video=media_file_id,
                    caption=card_text,
                    parse_mode="HTML",
                    cover=cover,
                    reply_markup=kb
                )
            except Exception:
                new_msg = await callback.message.answer_video(
                    video=media_file_id,
                    caption=card_text,
                    parse_mode="HTML",
                    reply_markup=kb
                )
        else:
            new_msg = await callback.message.answer_photo(
                photo=media_file_id,
                caption=card_text,
                parse_mode="HTML",
                reply_markup=kb
            )

        if new_msg:
            db.set_user_last_msg(callback.from_user.id, new_msg.message_id)

    await callback.answer()

# --- 🔍 Animelarni qidirish menyusi (Ro'yxat ko'rinishi) ---
@user_router.callback_query(F.data == "anime_search_menu")
async def search_anime_menu_callback(callback: CallbackQuery):
    animes = db.get_all_animes()
    if not animes:
        await callback.answer("Hozircha bazada animelar mavjud emas.", show_alert=True)
        return

    kb = get_anime_list_kb(animes, page=1)
    text = (
        "🔍 <b>Animelarni qidirish va tanlash</b>\n\n"
        "Quyidagi ro'yxatdan tomosha qilmoqchi bo'lgan animengizni tanlang yoki uning yonidagi <b>'Ko'rish'</b> tugmasini bosing:\n\n"
        "<i>Shuningdek, qidirayotgan anime nomini to'g'ridan-to'g'ri yozib yuborishingiz ham mumkin...</i>"
    )

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        sent_msg = await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        db.set_user_last_msg(callback.from_user.id, sent_msg.message_id)

    await callback.answer()

# --- Animelar ro'yxatida sahifalash (Pagination) ---
@user_router.callback_query(F.data.startswith("animelist_page_"))
async def anime_list_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    animes = db.get_all_animes()
    kb = get_anime_list_kb(animes, page=page)
    text = (
        "🔍 <b>Animelarni qidirish va tanlash</b>\n\n"
        "Quyidagi ro'yxatdan tomosha qilmoqchi bo'lgan animengizni tanlang yoki uning yonidagi <b>'Ko'rish'</b> tugmasini bosing:\n\n"
        "<i>Shuningdek, qidirayotgan anime nomini to'g'ridan-to'g'ri yozib yuborishingiz ham mumkin...</i>"
    )

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

# --- Ro'yxatdan anime tanlanganda (Nom yoki Ko'rish bosilganda) ---
@user_router.callback_query(F.data.startswith("open_anime_"))
async def open_anime_callback(callback: CallbackQuery):
    anime_id = int(callback.data.split("_")[2])

    # Ro'yxat turgan xabarni o'chirib, o'rniga to'g'ridan-to'g'ri o'sha animeni ochamiz
    try:
        await callback.message.delete()
    except Exception:
        pass

    await send_anime_card(callback.message, anime_id, user_id=callback.from_user.id)
    await callback.answer()

# --- Bosh sahifaga qaytish ---
@user_router.callback_query(F.data == "back_to_start")
async def back_to_start_callback(callback: CallbackQuery):
    user = callback.from_user
    text = (
        f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
        f"🎬 <b>Animem Uz</b> rasmiy anime botiga xush kelibsiz.\n"
        f"Bu yerda sevimli animelaringizni eng yuqori sifatda tomosha qilishingiz mumkin."
    )
    kb = get_start_kb()

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        db.set_user_last_msg(user.id, callback.message.message_id)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        sent_msg = await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        db.set_user_last_msg(user.id, sent_msg.message_id)

    await callback.answer()

@user_router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()

# --- Matn orqali qidiruv yoki keraksiz xabarlarni tozalash ---
@user_router.message()
async def clean_or_search_messages(message: Message):
    """
    Agar foydalanuvchi anime nomini qidirib matn yozsa, bazadan qidirib ro'yxat chiqaradi.
    Inline qidiruvdan tanlanganda (via_bot) chiqqan xabarni darhol o'chirib, botning O'ZI rasmiy xabar qilib tashlaydi.
    Boshqa barcha keraksiz narsalarni darhol o'chiradi.
    """
    user_id = message.from_user.id if message.from_user else None
    chat_type = message.chat.type if message.chat else ""

    # 1. AGAR XABAR INLINE QIDIRUV ORQALI YUBORILGAN BO'LSA (via @Animem_uz_bot):
    if message.via_bot:
        if chat_type == "private" and user_id:
            # 1. Anime ID sini aniqlash
            anime_id = None
            if message.reply_markup and message.reply_markup.inline_keyboard:
                for row in message.reply_markup.inline_keyboard:
                    for btn in row:
                        if btn.callback_data and btn.callback_data.startswith("watch_"):
                            try:
                                anime_id = int(btn.callback_data.split("_")[1])
                                break
                            except (IndexError, ValueError):
                                pass
                        elif btn.url and "start=anime_" in btn.url:
                            try:
                                anime_id = int(btn.url.split("start=anime_")[1].split("&")[0])
                                break
                            except (IndexError, ValueError):
                                pass
                    if anime_id:
                        break

            if anime_id is None:
                anime_id = _last_chosen_anime.get(user_id)

            if anime_id is None and message.caption:
                # Captionning birinchi qatoridagi nom bo'yicha qidirish
                first_line = message.caption.split("\n")[0].replace("📕", "").strip()
                matches = db.search_animes(first_line)
                if matches:
                    anime_id = matches[0]["id"]

            # 2. 'via @Animem_uz_bot' deb chiqqan xabarni DARHOL O'CHIRIB TASHLAYMIZ!
            try:
                await message.delete()
            except Exception:
                pass

            # 3. Avvalgi bot xabarini tozalaymiz
            await clean_previous_bot_message(message.bot, message.chat.id, user_id)

            # 4. Endi botning O'ZI to'g'ridan-to'g'ri rasmiy xabar qilib kartani tashlab beradi!
            if anime_id:
                await send_anime_card(message, anime_id, user_id=user_id)
        return

    # 2. Oddiy foydalanuvchi yozgan xabarlar:
    query = message.text.strip() if message.text else ""

    # User yozgan matnni o'chiramiz (chat toza turishi uchun)
    try:
        await message.delete()
    except Exception:
        pass

    if query:
        clean_query = query
        try:
            bot_info = await message.bot.get_me()
            if clean_query.startswith(f"@{bot_info.username}"):
                clean_query = clean_query.replace(f"@{bot_info.username}", "").strip()
        except Exception:
            pass
        if clean_query.startswith("@"):
            parts = clean_query.split(maxsplit=1)
            clean_query = parts[1] if len(parts) > 1 else ""

        if clean_query and len(clean_query) >= 2:
            found = db.search_animes(clean_query)
            if found:
                if user_id:
                    await clean_previous_bot_message(message.bot, message.chat.id, user_id)
                # Agar aynan 1 ta anime topilsa, to'g'ridan-to'g'ri o'sha animeni ochamiz
                if len(found) == 1:
                    await send_anime_card(message, found[0]["id"], user_id=user_id)
                else:
                    kb = get_anime_list_kb(found, page=1)
                    text = (
                        f"🔍 <b>'{clean_query}'</b> bo'yicha topilgan animelar:\n\n"
                        f"Tomosha qilmoqchi bo'lgan animengizni tanlang yoki 'Ko'rish' tugmasini bosing:"
                    )
                    sent_msg = await message.answer(text, parse_mode="HTML", reply_markup=kb)
                    if user_id:
                        db.set_user_last_msg(user_id, sent_msg.message_id)

