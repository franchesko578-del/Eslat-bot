# ESLATMA BOT

Telegram eslatma boti. Python + aiogram 3 + Supabase + Render.

## Imkoniyatlar
- Eslatma yaratish: matn, sana (YYYY-MM-DD), vaqt (HH:MM)
- Takrorlanish: bir marta, har kuni, har hafta, maxsus sana va vaqt
- Eslatmalarim: ko'rish, tahrirlash, o'chirish
- Admin (/admin): statistika va hammaga xabar yuborish
- Vaqt zonasi: Asia/Tashkent
- Eslatmalar Supabase bazasida saqlanadi, bot qayta ishga tushsa yo'qolmaydi

## Papkalar
    app/bot.py            asosiy fayl
    app/config.py         sozlamalar
    app/db.py             Supabase bilan ishlash
    app/keyboards.py      tugmalar
    app/scheduler.py      eslatma yuboruvchi
    app/handlers/         buyruq va tugma ishlovchilari
    supabase_schema.sql   baza jadvallari
    render.yaml           Render sozlamasi

## Qisqa yo'riqnoma
1. BotFather'dan token oling.
2. Supabase'da loyiha oching, supabase_schema.sql ni SQL Editor'da RUN qiling.
3. Hamma fayllarni GitHub'ga yuklang (.env yuklanmaydi).
4. Render'da Blueprint yoki Web Service yarating:
   - Build: `pip install -r requirements.txt`
   - Start: `python -m app.bot`
   - Environment: BOT_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_ID, TIMEZONE
5. UptimeRobot bilan `https://SIZNING-NOM.onrender.com/health` manzilini
   har 5 daqiqada tekshirtiring (bepul tarifda bot uxlab qolmasligi uchun).

To'liq yo'riqnoma PDF hujjatda.
