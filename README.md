# ESLATMA BOT

Telegram eslatma boti. Python + aiogram 3 + Supabase + Render.

## Imkoniyatlar
- Tez yozish: "ertaga 9:00 dori ichish", "30 daqiqadan keyin choy", "har kuni 8 00 vitamin". Soat 9, 9 00, 9:00, soat 9 da kabi yoziladi
- Eslatma yaratish: matn, sana va vaqt. Vaqtni tugma bilan tanlash (08:00, 09:00, 12:00, 18:00, 21:00) yoki yozish mumkin
- Eslatma kelganda tugmalar: Bajarildi, 10 daqiqadan keyin, 1 soatdan keyin
- Do'stga eslatma: havola orqali boshqa odamga eslatma yuborish
- Takrorlanish: bir marta, har kuni, har hafta, maxsus sana va vaqt
- Eslatmalarim: ko'rish, tahrirlash, o'chirish
- Admin (/admin): statistika, kunlik faol foydalanuvchilar, hammaga xabar yuborish
- Vaqt zonasi: Asia/Tashkent
- Eslatmalar Supabase bazasida saqlanadi, bot qayta ishga tushsa yo'qolmaydi

## Papkalar
    app/bot.py            asosiy fayl
    app/config.py         sozlamalar
    app/db.py             Supabase bilan ishlash
    app/quick.py          tez yozish (matndan sana va vaqtni ajratish)
    app/sharing.py        do'stga eslatma havolalari
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

## Ro'yxatdan o'tish va xavfsizlik imkoniyatlari
- /start da foydalanish shartlari ko'rsatiladi; foydalanuvchi alohida rozilik beradi.
- Telefon raqami Telegram'ning `request_contact` tugmasi orqali olinadi. Faqat o'z raqami qabul qilinadi.
- Ro'yxatdan o'tish ikki bosqichli: rozilik, keyin telefon. Lokatsiya so'ralmaydi.
- Admin panelida foydalanuvchilar, profil ma'lumotlari, telefon, bloklash va xabarlar jurnali mavjud.
- Admin majburiy obuna kanallarini qo'shishi/o'chirishi mumkin. Kanal tekshiruvi uchun bot kanalga administrator qilib qo'yilishi kerak.
- Xabarlar jurnali rozilikdan keyin yuborilgan matnli xabarlarni qayd etadi; maxfiy kodlar/parollar yubormaslik tavsiya etiladi.

### Supabase yangilash
Supabase -> SQL Editor -> New query bo'limida `supabase_schema.sql` faylining to'liq mazmunini ishga tushiring. Fayl mavjud `users`, `reminders` va `reminder_logs` jadvallarini saqlab, yangi ustun va jadvallarni qo'shadi.
