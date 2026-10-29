import math
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def get_admin_main_kb() -> ReplyKeyboardMarkup:
    """Admin boshqaruv paneli menyusi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ Yangi anime qo'shish"),
                KeyboardButton(text="🎬 Epizod qo'shish / oshirish")
            ],
            [
                KeyboardButton(text="📋 Animelar ro'yxati"),
                KeyboardButton(text="📊 Statistika")
            ]
        ],
        resize_keyboard=True
    )

def get_cancel_kb() -> ReplyKeyboardMarkup:
    """Jarayonni bekor qilish tugmasi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def get_finish_episodes_kb() -> ReplyKeyboardMarkup:
    """Epizodlarni yuklash jarayonini yakunlash tugmasi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Yuklashni yakunlash")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def get_start_kb() -> InlineKeyboardMarkup:
    """
    Start xabari tagidagi yashil rangdagi '🔍 Animelarni qidirish' tugmasi
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Animelarni qidirish",
                    callback_data="anime_search_menu",
                    style="success"
                )
            ]
        ]
    )

def get_anime_list_kb(animes: list, page: int = 1, per_page: int = 6) -> InlineKeyboardMarkup:
    """
    '🔍 Animelarni qidirish' bosilganda chiqadigan animelar ro'yxati.
    Har bir anime nomi va yonida '👁️ Ko'rish' yozuvli yashil tugma bo'ladi.
    """
    if not animes:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Bosh sahifaga qaytish", callback_data="back_to_start", style="danger")]
            ]
        )

    total_animes = len(animes)
    total_pages = max(1, math.ceil(total_animes / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_animes = animes[start_idx:end_idx]

    keyboard = []
    for a in page_animes:
        title = a["title"]
        if len(title) > 22:
            title = title[:20] + ".."
        keyboard.append([
            InlineKeyboardButton(text=f"🎬 {title}", callback_data=f"open_anime_{a['id']}"),
            InlineKeyboardButton(text="👁️ Ko'rish", callback_data=f"open_anime_{a['id']}", style="success")
        ])

    # Sahifalash (agar 1 tadan ko'p sahifa bo'lsa)
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"animelist_page_{page - 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data="noop", style="primary"))

        nav_row.append(InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data="noop", style="success"))

        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"animelist_page_{page + 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data="noop", style="primary"))

        keyboard.append(nav_row)

    # Bosh sahifaga qaytish tugmasi
    keyboard.append([
        InlineKeyboardButton(text="🔙 Bosh sahifaga qaytish", callback_data="back_to_start", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_anime_card_kb(anime_id: int, total_episodes: int) -> InlineKeyboardMarkup:
    """
    1-rasmdagi ko'rinish:
    Karta tagidagi katta yashil 'Tomosha qilish' tugmasi (style='success')
    va '🔍 Boshqa animelar' tugmasi
    """
    ep_label = f"▶️ Tomosha qilish ( {total_episodes} epizod )" if total_episodes > 0 else "▶️ Tomosha qilish (Tez kunda)"
    buttons = [
        [
            InlineKeyboardButton(text=ep_label, callback_data=f"watch_{anime_id}_1", style="success")
        ],
        [
            InlineKeyboardButton(text="🔍 Boshqa animelar", callback_data="anime_search_menu", style="primary")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_episode_grid_kb(anime_id: int, current_ep: int, episode_numbers: list, page: int = 1, per_page: int = 12) -> InlineKeyboardMarkup:
    """
    2-rasmdagi ko'rinish:
    12 talik disklardan iborat rangli epizodlar paneli va sahifalash (pagination)
    """
    if not episode_numbers:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"card_{anime_id}", style="primary")]
        ])

    total_episodes = len(episode_numbers)
    total_pages = max(1, math.ceil(total_episodes / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_episodes = episode_numbers[start_idx:end_idx]

    keyboard = []
    row = []

    # Epizodlarni 3 tadan qilib qatorga terish (Ko'k va Yashil ranglar bilan)
    for ep_num in page_episodes:
        if ep_num == current_ep:
            # Hozirgi tanlangan qism yashil (success) rangda
            btn_text = f"▶️ {ep_num} ep"
            btn_style = "success"
        else:
            # Boshqa qismlar moviy/ko'k (primary) rangda
            btn_text = f"💿 {ep_num} ep"
            btn_style = "primary"

        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"ep_{anime_id}_{ep_num}_{page}", style=btn_style))

        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    # Sahifalash (Pagination) qatori: Oldingi/Keyingi doim ko'k (primary), o'rtadagi 1/15 yashil (success)
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page_{anime_id}_{current_ep}_{page - 1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data="noop", style="primary"))

    # 2-rasmdagi kabi markaziy sahifa ko'rsatkichi yashil rangda
    nav_row.append(InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data="noop", style="success"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page_{anime_id}_{current_ep}_{page + 1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data="noop", style="primary"))

    keyboard.append(nav_row)

    # Asosiy kartaga qaytish tugmasi qizil (danger) rangda
    keyboard.append([
        InlineKeyboardButton(text="📕 Anime ma'lumotlariga qaytish", callback_data=f"card_{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

