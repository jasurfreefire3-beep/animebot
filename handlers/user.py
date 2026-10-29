import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaVideo, InputMediaPhoto, FSInputFile
from aiogram.filters import CommandStart, CommandObject

from database import Database
from keyboards import get_anime_card_kb, get_episode_grid_kb
from utils.tracker import watchers_tracker, get_fast_banner_cover

user_router = Router()
db = Database()

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

    # Oddiy /start
    animes = db.get_all_animes()
    text = (
        f"👋 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
        f"🎬 <b>Animem Uz</b> rasmiy anime botiga xush kelibsiz.\n"
        f"Bu yerda sevimli animelaringizni eng yuqori sifatda tomosha qilishingiz mumkin.\n\n"
    )

    if animes:
        text += "🔥 <b>Mavjud animelar:</b>\n"
        for a in animes[:10]:
            ep_count = db.get_episode_count(a["id"])
            text += f"• /start anime_{a['id']} — <b>{a['title']}</b> ({ep_count} ep)\n"
    else:
        text += "<i>Hozircha animelar yuklanmoqda...</i>"

    sent_msg = await message.answer(text, parse_mode="HTML")
    db.set_user_last_msg(user.id, sent_msg.message_id)

async def send_anime_card(message: Message, anime_id: int):
    user_id = message.from_user.id
    anime = db.get_anime(anime_id)
    if not anime:
        sent_err = await message.answer("Kechirasiz, ushbu anime topilmadi yoki o'chirilgan.")
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

    if sent_msg:
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
            # Agar mavjud xabarda video bo'lsa, uning mediasini almashtiramiz
            await callback.message.edit_media(
                media=InputMediaVideo(media=video_id, caption=player_text, parse_mode="HTML", cover=cover),
                reply_markup=kb
            )
            db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
        except Exception:
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
            await callback.message.edit_caption(
                caption=player_text,
                parse_mode="HTML",
                reply_markup=kb
            )
            db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
        except Exception:
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

    try:
        if media_type == "video":
            await callback.message.edit_media(
                media=InputMediaVideo(media=media_file_id, caption=card_text, parse_mode="HTML", cover=cover),
                reply_markup=kb
            )
        else:
            await callback.message.edit_media(
                media=InputMediaPhoto(media=media_file_id, caption=card_text, parse_mode="HTML"),
                reply_markup=kb
            )
        db.set_user_last_msg(callback.from_user.id, callback.message.message_id)
    except Exception:
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

@user_router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()

# --- Har qanday keraksiz xabarlarni darhol o'chirish ---
@user_router.message()
async def clean_unwanted_messages(message: Message):
    """
    Foydalanuvchi yozgan har qanday matn, stiker, rasm yoki buyruqlarni
    chat toza turishi uchun avtomatik o'chirib tashlaydi.
    """
    try:
        await message.delete()
    except Exception:
        pass

