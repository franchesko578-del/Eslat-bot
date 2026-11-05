-- ESLATMA BOT uchun Supabase bazasi.
-- Supabase -> SQL Editor -> New query -> shu kodni qo'yib RUN bosing.
-- Kodni qayta ishga tushirsangiz ham xato bermaydi.

create table if not exists public.users (
    telegram_id  bigint primary key,
    full_name    text,
    username     text,
    created_at   timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

create table if not exists public.reminders (
    id          bigint generated always as identity primary key,
    user_id     bigint not null,
    text        text not null,
    remind_at   timestamptz not null,
    repeat_type text not null default 'once'
                check (repeat_type in ('once', 'daily', 'weekly')),
    status      text not null default 'active'
                check (status in ('active', 'done', 'failed')),
    fail_count  integer not null default 0,
    created_at  timestamptz not null default now()
);

create table if not exists public.reminder_logs (
    id          bigint generated always as identity primary key,
    reminder_id bigint,
    user_id     bigint not null,
    ok          boolean not null,
    error       text,
    sent_at     timestamptz not null default now()
);

create index if not exists reminders_due_idx
    on public.reminders (status, remind_at);
create index if not exists reminders_user_idx
    on public.reminders (user_id, status, remind_at);
create index if not exists logs_sent_idx
    on public.reminder_logs (ok, sent_at);

-- Xavfsizlik: jadvallarni tashqaridan (anon kalit bilan) ochiq qoldirmaymiz.
-- Bot "service_role" kaliti bilan ishlaydi, u bu cheklovdan o'tadi.
alter table public.users enable row level security;
alter table public.reminders enable row level security;
alter table public.reminder_logs enable row level security;
