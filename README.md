# ESLATMA BOT

Telegram eslatma boti. Python + aiogram 3 + Supabase + Render.

## Imkoniyatlar
- Tez yozish: "ertaga 9:00 dori ichish", "30 daqiqadan keyin choy", "har dushanba, juma 18:00 futbol", "har 3 kunda 9:00 dori". Soat 9, 9 00, 9:00, soat 9 da kabi yoziladi
- Eslatma yaratish: matn, sana, so'ng soat (00-23) va minut (00-59) tugmalari
- Takrorlash: har kuni, hafta kunlari (Du, Chor, Ju...), har hafta, har oy, har N kunda
- Eslatma kelganda tugmalar: 5, 10, 15 daqiqa, 1 soat, ertaga, Bajarildi
- Oldindan ogohlantirish (Sozlamalar): eslatmadan 5-60 daqiqa oldin xabar
- Ertalabki ro'yxat (Sozlamalar): har ertalab bugungi eslatmalar ro'yxati
- Bot xatoga uchrasa, adminga Telegram orqali xabar keladi
- Barcha tugmalar rangli (Telegram'ning yangi `style` imkoniyati)
- Do'stga eslatma: havola orqali boshqa odamga eslatma yuborish
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
    app/alerts.py         adminga xato haqida xabar
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
- /start da akkaunt telefon raqami orqali tasdiqlanadi.
- Telefon raqami Telegram'ning `request_contact` tugmasi orqali olinadi. Faqat o'z raqami qabul qilinadi.
- Lokatsiya so'ralmaydi.
- Admin panelida foydalanuvchilar, profil ma'lumotlari, telefon, bloklash va xabarlar jurnali mavjud.
- Admin majburiy obuna kanallarini qo'shishi/o'chirishi mumkin. Kanal tekshiruvi uchun bot kanalga administrator qilib qo'yilishi kerak.
- Xabarlar jurnali rozilikdan keyin yuborilgan matnli xabarlarni qayd etadi; maxfiy kodlar/parollar yubormaslik tavsiya etiladi.

### Supabase yangilash
Supabase -> SQL Editor -> New query bo'limida `supabase_schema.sql` faylining to'liq mazmunini ishga tushiring. Fayl mavjud `users`, `reminders` va `reminder_logs` jadvallarini saqlab, yangi ustun va jadvallarni qo'shadi.
