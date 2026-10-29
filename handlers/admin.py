from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from database import Database
from keyboards import (
    get_admin_main_kb,
    get_cancel_kb,
    get_finish_episodes_kb,
    get_anime_card_kb
)
from utils.parser import extract_episode_number

admin_router = Router()
db = Database()

class AddAnimeState(StatesGroup):
    title = State()
    genres = State()
    year = State()
    media = State()

class EditAnimeState(StatesGroup):
    waiting_title = State()
    waiting_genres = State()
    waiting_year = State()
    waiting_media = State()

class AddEpisodesState(StatesGroup):
    uploading = State()

def is_admin(user_id: int) -> bool:
    """Foydalanuvchi admin ekanligini tekshiradi"""
    if not ADMIN_IDS:
        return True  # Agar admin belgilanmagan bo'lsa, test uchun ruxsat beriladi
    return user_id in ADMIN_IDS

# --- /admin Asosiy menyu ---
@admin_router.message(Command("admin"))
async def admin_panel_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        return

    try:
        await message.delete()
    except Exception:
        pass

    await state.clear()
    await message.answer(
        "👋 <b>Anime Bot Boshqaruv Paneliga xush kelibsiz!</b>\n\n"
        "Quyidagi menyu orqali yangi anime qo'shishingiz, mavjudlarini tahrirlashingiz, epizodlarni yuklashingiz yoki statistikani ko'rishingiz mumkin:",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb()
    )

@admin_router.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        return

    await state.clear()
    await message.answer(
        "Amal bekor qilindi.",
        reply_markup=get_admin_main_kb()
    )

# --- 1. Yangi Anime Qo'shish ---
@admin_router.message(F.text == "➕ Yangi anime qo'shish")
async def start_add_anime(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        return

    await state.set_state(AddAnimeState.title)
    await message.answer(
        "🎬 <b>1-qadam:</b> Anime nomini kiriting:\n"
        "<i>(Masalan: Qora Klever / Black Clover)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )

@admin_router.message(AddAnimeState.title)
async def process_anime_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Iltimos, to'g'ri nom kiriting:")
        return

    await state.update_data(title=title)
    await state.set_state(AddAnimeState.genres)
    await message.answer(
        "🏷️ <b>2-qadam:</b> Janrlarni kiriting:\n"
        "<i>(Masalan: Jangari • Sarguzasht • Komediya • Fantaziya)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )

@admin_router.message(AddAnimeState.genres)
async def process_anime_genres(message: Message, state: FSMContext):
    genres = message.text.strip()
    if not genres:
        await message.answer("Iltimos, janrlarni kiriting:")
        return

    await state.update_data(genres=genres)
    await state.set_state(AddAnimeState.year)
    await message.answer(
        "📅 <b>3-qadam:</b> Chiqarilgan yilini kiriting:\n"
        "<i>(Masalan: 2024 yoki 2017)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )

@admin_router.message(AddAnimeState.year)
async def process_anime_year(message: Message, state: FSMContext):
    raw = message.text.strip()
    year = 2024
    if raw.isdigit() and len(raw) == 4:
        year = int(raw)

    await state.update_data(year=year)
    await state.set_state(AddAnimeState.media)
    await message.answer(
        "📹 <b>4-qadam:</b> Anime uchun <b>qisqa video (treyler)</b> yoki <b>poster rasm</b> yuboring:\n"
        "<i>(Ushbu media foydalanuvchiga anime kartasida ko'rinadi)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )

@admin_router.message(AddAnimeState.media)
async def process_anime_media(message: Message, state: FSMContext, bot: Bot):
    media_type = None
    media_file_id = None

    if message.video:
        media_type = "video"
        media_file_id = message.video.file_id
    elif message.animation:
        media_type = "video"
        media_file_id = message.animation.file_id
    elif message.photo:
        media_type = "photo"
        media_file_id = message.photo[-1].file_id
    else:
        await message.answer("Iltimos, video yoki rasm yuboring:")
        return

    data = await state.get_data()
    title = data["title"]
    genres = data["genres"]
    year = data.get("year", 2024)

    # Bazaga saqlash
    anime_id = db.add_anime(
        title=title,
        genres=genres,
        media_type=media_type,
        media_file_id=media_file_id,
        year=year
    )

    await state.clear()

    # Auto-start link yaratish
    bot_user = await bot.get_me()
    start_link = f"https://t.me/{bot_user.username}?start=anime_{anime_id}"

    # Tezkor epizod yuklash tugmasi
    action_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Epizodlarni yuklashni boshlash", callback_data=f"admin_add_eps_{anime_id}")],
        [InlineKeyboardButton(text="✏️ Animeni tahrirlash", callback_data=f"admin_edit_{anime_id}")]
    ])

    await message.answer(
        f"✅ <b>Anime muvaffaqiyatli saqlandi!</b>\n\n"
        f"📕 <b>Nomi:</b> {title}\n"
        f"🏷️ <b>Janrlar:</b> {genres}\n"
        f"📅 <b>Yili:</b> {year}\n"
        f"🆔 <b>Anime ID:</b> <code>{anime_id}</code>\n\n"
        f"🔗 <b>Kanalingizga qo'yish uchun Auto-Start havolasi:</b>\n"
        f"<code>{start_link}</code>\n\n"
        f"<i>Ushbu havolani Telegram kanalingizdagi postga ulasangiz, odamlar bitta bosishda shu animeni ochishadi.</i>",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb()
    )

    await message.answer(
        "Endi ushbu animega epizodlarni yuklashni yoki tahrirlashni xohlaysizmi?",
        reply_markup=action_kb
    )

# --- 2. Epizod qo'shish / oshirish ---
@admin_router.message(F.text == "🎬 Epizod qo'shish / oshirish")
async def choose_anime_for_episodes(message: Message):
    if not is_admin(message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        return

    animes = db.get_all_animes()
    if not animes:
        await message.answer("Hozircha bazada birorta ham anime yo'q. Avval anime qo'shing.")
        return

    buttons = []
    for a in animes[:30]:
        ep_count = db.get_episode_count(a["id"])
        buttons.append([
            InlineKeyboardButton(
                text=f"{a['title']} ({ep_count} ep)",
                callback_data=f"admin_add_eps_{a['id']}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "Qaysi animega epizod qo'shmoqchisiz? Tanlang:",
        reply_markup=kb
    )

@admin_router.callback_query(F.data.startswith("admin_add_eps_"))
async def start_uploading_episodes(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    anime_id = int(callback.data.split("_")[3])
    anime = db.get_anime(anime_id)
    if not anime:
        await callback.answer("Anime topilmadi!", show_alert=True)
        return

    current_count = db.get_episode_count(anime_id)
    await state.set_state(AddEpisodesState.uploading)
    await state.update_data(anime_id=anime_id, added_count=0)

    await callback.message.answer(
        f"🎬 <b>'{anime['title']}'</b> uchun epizodlarni qabul qilish boshlandi!\n\n"
        f"📊 Hozirgi epizodlar soni: <b>{current_count} ta</b>\n\n"
        f"📤 <b>Ko'rsatma:</b>\n"
        f"• Videolarni bittalab yoki guruhlab (forward/media group) yuboring.\n"
        f"• Agar videoning izohida (caption) qism ko'rsatilgan bo'lsa (masalan: <i>'1-qism'</i> yoki <i>'Episode 5'</i>), bot qism raqamini avtomatik aniqlaydi.\n"
        f"• Agar izoh bo'lmasa, navbatdagi tartib raqamini avtomatik beradi.\n\n"
        f"<i>Yuklab bo'lgach, pastdagi '✅ Yuklashni yakunlash' tugmasini bosing.</i>",
        parse_mode="HTML",
        reply_markup=get_finish_episodes_kb()
    )
    await callback.answer()

@admin_router.message(AddEpisodesState.uploading, F.video)
async def handle_episode_video(message: Message, state: FSMContext):
    data = await state.get_data()
    anime_id = data["anime_id"]
    added_count = data.get("added_count", 0)

    caption = message.caption or (message.video.file_name if message.video else "") or ""
    detected_ep = extract_episode_number(caption)

    if detected_ep is None or detected_ep <= 0:
        max_ep = db.get_max_episode_number(anime_id)
        detected_ep = max_ep + 1

    db.add_or_update_episode(
        anime_id=anime_id,
        episode_number=detected_ep,
        video_file_id=message.video.file_id,
        caption=caption
    )

    added_count += 1
    await state.update_data(added_count=added_count)
    total_episodes = db.get_episode_count(anime_id)

    await message.reply(
        f"✅ <b>{detected_ep}-epizod muvaffaqiyatli saqlandi!</b>\n"
        f"Jami yuklangan: {total_episodes} ta",
        parse_mode="HTML"
    )

@admin_router.message(AddEpisodesState.uploading, F.text == "✅ Yuklashni yakunlash")
async def finish_uploading_episodes(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    added_count = data.get("added_count", 0)

    await state.clear()

    if not anime_id:
        await message.answer("Jarayon yakunlandi.", reply_markup=get_admin_main_kb())
        return

    anime = db.get_anime(anime_id)
    total_episodes = db.get_episode_count(anime_id)

    bot_user = await bot.get_me()
    start_link = f"https://t.me/{bot_user.username}?start=anime_{anime_id}"

    await message.answer(
        f"🎉 <b>Yuklash yakunlandi!</b>\n\n"
        f"📕 <b>Anime:</b> {anime['title'] if anime else ''}\n"
        f"📥 Ushbu sessiyada qo'shildi: <b>{added_count} ta</b>\n"
        f"📺 <b>Jami epizodlar:</b> {total_episodes} ta\n\n"
        f"🔗 <b>Auto-Start havolasi:</b>\n"
        f"<code>{start_link}</code>",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb()
    )

# --- 3. Animelar ro'yxati va Tahrirlash ---
@admin_router.message(F.text == "📋 Animelar ro'yxati")
@admin_router.callback_query(F.data == "admin_list_animes")
async def list_animes_handler(event: Message | CallbackQuery, bot: Bot):
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, Message):
            try:
                await event.delete()
            except Exception:
                pass
        return

    animes = db.get_all_animes()
    target_msg = event if isinstance(event, Message) else event.message

    if not animes:
        await target_msg.answer("Hozircha birorta ham anime qo'shilmagan.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return

    bot_user = await bot.get_me()
    text = "📋 <b>Bazada mavjud animelar:</b>\n\n"

    buttons = []
    for idx, a in enumerate(animes[:25], 1):
        ep_count = db.get_episode_count(a["id"])
        year = a.get("year", 2024)
        text += (
            f"<b>{idx}. {a['title']}</b> ({year})\n"
            f"   Epizodlar: {ep_count} ta | Ko'rishlar: {a['views']}\n"
            f"   Havola: <code>https://t.me/{bot_user.username}?start=anime_{a['id']}</code>\n\n"
        )
        buttons.append([
            InlineKeyboardButton(text=f"✏️ {a['title'][:16]}", callback_data=f"admin_edit_{a['id']}"),
            InlineKeyboardButton(text="🎬 (+ep)", callback_data=f"admin_add_eps_{a['id']}"),
            InlineKeyboardButton(text="🗑️", callback_data=f"admin_del_{a['id']}")
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await event.message.answer(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

# --- Animeni Tahrirlash Menyu ---
@admin_router.callback_query(F.data.startswith("admin_edit_"))
async def edit_anime_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    anime_id = int(callback.data.split("_")[2])
    anime = db.get_anime(anime_id)
    if not anime:
        await callback.answer("Anime topilmadi!", show_alert=True)
        return

    await state.clear()
    ep_count = db.get_episode_count(anime_id)

    text = (
        f"✏️ <b>Anime Tahrirlash:</b>\n\n"
        f"📕 <b>Nomi:</b> {anime['title']}\n"
        f"🏷️ <b>Janrlar:</b> {anime['genres']}\n"
        f"📅 <b>Yili:</b> {anime.get('year', 2024)}\n"
        f"📺 <b>Epizodlar:</b> {ep_count} ta\n"
        f"👁️ <b>Ko'rishlar:</b> {anime['views']}\n\n"
        f"Qaysi ma'lumotni o'zgartirmoqchisiz? Quyidagilardan birini tanlang:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Nomini o'zgartirish", callback_data=f"edit_field_{anime_id}_title"),
            InlineKeyboardButton(text="🏷️ Janrlarni o'zgartirish", callback_data=f"edit_field_{anime_id}_genres")
        ],
        [
            InlineKeyboardButton(text="📅 Yilini o'zgartirish", callback_data=f"edit_field_{anime_id}_year"),
            InlineKeyboardButton(text="🖼️ Rasm/Videoni yangilash", callback_data=f"edit_field_{anime_id}_media")
        ],
        [
            InlineKeyboardButton(text="🔙 Animelar ro'yxatiga qaytish", callback_data="admin_list_animes")
        ]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@admin_router.callback_query(F.data.startswith("edit_field_"))
async def handle_edit_field_request(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split("_")
    anime_id = int(parts[2])
    field = parts[3]

    anime = db.get_anime(anime_id)
    if not anime:
        await callback.answer("Anime topilmadi!", show_alert=True)
        return

    await state.update_data(edit_anime_id=anime_id)

    if field == "title":
        await state.set_state(EditAnimeState.waiting_title)
        await callback.message.answer(
            f"✏️ <b>'{anime['title']}'</b> uchun yangi nom kiriting:",
            parse_mode="HTML",
            reply_markup=get_cancel_kb()
        )
    elif field == "genres":
        await state.set_state(EditAnimeState.waiting_genres)
        await callback.message.answer(
            f"🏷️ Yangi janrlarni kiriting (hozirgi: <i>{anime['genres']}</i>):",
            parse_mode="HTML",
            reply_markup=get_cancel_kb()
        )
    elif field == "year":
        await state.set_state(EditAnimeState.waiting_year)
        await callback.message.answer(
            f"📅 Yangi chiqarilgan yilini kiriting (hozirgi: <i>{anime.get('year', 2024)}</i>):",
            parse_mode="HTML",
            reply_markup=get_cancel_kb()
        )
    elif field == "media":
        await state.set_state(EditAnimeState.waiting_media)
        await callback.message.answer(
            "🖼️ Yangi <b>video (treyler)</b> yoki <b>poster rasm</b> yuboring:",
            parse_mode="HTML",
            reply_markup=get_cancel_kb()
        )

    await callback.answer()

@admin_router.message(EditAnimeState.waiting_title)
async def process_new_title(message: Message, state: FSMContext):
    new_title = message.text.strip()
    data = await state.get_data()
    anime_id = data["edit_anime_id"]

    db.update_anime_field(anime_id, "title", new_title)
    await state.clear()
    await message.answer(
        f"✅ Anime nomi muvaffaqiyatli yangilandi: <b>{new_title}</b>",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb()
    )

@admin_router.message(EditAnimeState.waiting_genres)
async def process_new_genres(message: Message, state: FSMContext):
    new_genres = message.text.strip()
    data = await state.get_data()
    anime_id = data["edit_anime_id"]

    db.update_anime_field(anime_id, "genres", new_genres)
    await state.clear()
    await message.answer(
        f"✅ Janrlar muvaffaqiyatli yangilandi: <b>{new_genres}</b>",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb()
    )

@admin_router.message(EditAnimeState.waiting_year)
async def process_new_year(message: Message, state: FSMContext):
    raw = message.text.strip()
    if not raw.isdigit() or len(raw) != 4:
        await message.answer("Iltimos, 4 xonali to'g'ri yil kiriting (masalan: 2024):")
        return

    year = int(raw)
    data = await state.get_data()
    anime_id = data["edit_anime_id"]

    db.update_anime_field(anime_id, "year", year)
    await state.clear()
    await message.answer(
        f"✅ Chiqarilgan yili muvaffaqiyatli yangilandi: <b>{year}</b>",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb()
    )

@admin_router.message(EditAnimeState.waiting_media)
async def process_new_media(message: Message, state: FSMContext):
    media_type = None
    media_file_id = None

    if message.video:
        media_type = "video"
        media_file_id = message.video.file_id
    elif message.animation:
        media_type = "video"
        media_file_id = message.animation.file_id
    elif message.photo:
        media_type = "photo"
        media_file_id = message.photo[-1].file_id
    else:
        await message.answer("Iltimos, video yoki rasm yuboring:")
        return

    data = await state.get_data()
    anime_id = data["edit_anime_id"]

    db.update_anime_field(anime_id, "media_type", media_type)
    db.update_anime_field(anime_id, "media_file_id", media_file_id)
    await state.clear()
    await message.answer(
        "✅ Anime muqovasi (rasm/video) muvaffaqiyatli yangilandi!",
        parse_mode="HTML",
        reply_markup=get_admin_main_kb()
    )

@admin_router.callback_query(F.data.startswith("admin_del_"))
async def delete_anime_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    anime_id = int(callback.data.split("_")[2])
    db.delete_anime(anime_id)
    await callback.answer("Anime o'chirildi!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass

# --- 4. Statistika ---
@admin_router.message(F.text == "📊 Statistika")
async def stats_handler(message: Message):
    if not is_admin(message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        return

    users_count = db.get_users_count()
    animes = db.get_all_animes()
    total_views = sum(a["views"] for a in animes)
    total_episodes = sum(db.get_episode_count(a["id"]) for a in animes)

    await message.answer(
        f"📊 <b>Bot Statistikasi:</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users_count} ta</b>\n"
        f"🎬 Animelar: <b>{len(animes)} ta</b>\n"
        f"📺 Jami Epizodlar: <b>{total_episodes} ta</b>\n"
        f"👁️ Jami ko'rishlar: <b>{total_views} marta</b>",
        parse_mode="HTML"
    )
