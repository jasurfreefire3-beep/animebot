# 🎬 Animem Uz Telegram Bot

Telegram orqali professional anime tomosha qilish va yuklash platformasi boti.

## ✨ Imkoniyatlar:
- 📺 **Telegram Blockquote Player:** Zamonaviy ko'k chiziqli va ramkali dizayn.
- 🎨 **Rangli tugmalar:** Telegram yangi Bot API rangli tugmalari (Yashil, To'q Ko'k, Qizil).
- 🟢 **Haqiqiy tomoshabinlar (Real Watchers Tracker):** Soxta sonlarsiz, 15 daqiqa ichida faol tomosha qilayotgan haqiqiy foydalanuvchilar ismlari bilan ko'rsatiladi.
- ⚡ **0.05s Tezkor Kesh:** `baner.png` muqova rasmi Telegram serverida `file_id` orqali keshlanadi va videolarga bir zumda ulanadi.
- 🔗 **Auto-Start havolalar:** Har bir anime uchun kanalga joylashga mo'ljallangan qulay havola (`t.me/Animem_uz_bot?start=anime_ID`).
- 🧹 **Avtomatik tozalash (Clean Chat):** Foydalanuvchi buyruqlari va eski anime kartalari avtomatik o'chirilib, chat doimo toza saqlanadi.
- 👑 **To'liq Admin Panel (`/admin`):** Anime qo'shish, chiqarilgan yilini belgilash, tahrirlash (nom, janr, yil, media), epizodlarni ommaviy yuklash va statistika. Begonalardan to'liq yashiringan.

---

## 🚀 Railway.app ga o'rnatish (Deploy):

1. [Railway.app](https://railway.app) ga kiring va GitHub hisobingiz bilan tizimga kiring.
2. **"New Project"** &rarr; **"Deploy from GitHub repo"** ni tanlang va `animebot` omborini tanlang.
3. **Variables** bo'limida quyidagi o'zgaruvchilarni qo'shing:
   - `BOT_TOKEN`: Sizning bot tokeningiz (masalan: `9232544560:AAEaoCjy4DmJ8E5zZBwnzd2S4EOPrQNNttY`)
   - `ADMIN_IDS`: Admin Telegram ID raqami (masalan: `8278030347`)
   - `DATABASE_PATH`: `anime_bot.db` (yoki Railway Volume ulanganda `/data/anime_bot.db`)
4. **Deploy** tugmasini bosing! Bot avtomatik tarzda Docker orqali quriladi va 24/7 ishlab turadi.
