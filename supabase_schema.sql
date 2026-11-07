-- ESLATMA BOT: yangi baza va mavjud bazani yangilash uchun xavfsiz sxema.
create table if not exists public.users (
    telegram_id bigint primary key,
    full_name text,
    username text,
    phone text,
    consent boolean not null default false,
    consent_at timestamptz,
    latitude double precision,
    longitude double precision,
    location_shared_at timestamptz,
    is_blocked boolean not null default false,
    created_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

alter table public.users add column if not exists phone text;
alter table public.users add column if not exists consent boolean not null default false;
alter table public.users add column if not exists consent_at timestamptz;
alter table public.users add column if not exists latitude double precision;
alter table public.users add column if not exists longitude double precision;
alter table public.users add column if not exists location_shared_at timestamptz;
alter table public.users add column if not exists is_blocked boolean not null default false;

create table if not exists public.reminders (
    id bigint generated always as identity primary key,
    user_id bigint not null,
    text text not null,
    remind_at timestamptz not null,
    repeat_type text not null default 'once' check (repeat_type in ('once','daily','weekly')),
    status text not null default 'active' check (status in ('active','done','failed')),
    fail_count integer not null default 0,
    created_at timestamptz not null default now()
);
create table if not exists public.reminder_logs (
    id bigint generated always as identity primary key,
    reminder_id bigint,
    user_id bigint not null,
    ok boolean not null,
    error text,
    sent_at timestamptz not null default now()
);
create table if not exists public.message_logs (
    id bigint generated always as identity primary key,
    telegram_id bigint not null references public.users(telegram_id) on delete cascade,
    direction text not null,
    message_type text not null default 'text',
    content text not null,
    created_at timestamptz not null default now()
);
create table if not exists public.required_channels (
    id bigint generated always as identity primary key,
    chat_id text not null unique,
    title text not null,
    invite_link text,
    created_at timestamptz not null default now()
);
create index if not exists reminders_due_idx on public.reminders(status, remind_at);
create index if not exists reminders_user_idx on public.reminders(user_id, status, remind_at);
create index if not exists logs_sent_idx on public.reminder_logs(ok, sent_at);
create index if not exists message_logs_user_time_idx on public.message_logs(telegram_id, created_at desc);
alter table public.users enable row level security;
alter table public.reminders enable row level security;
alter table public.reminder_logs enable row level security;
alter table public.message_logs enable row level security;
alter table public.required_channels enable row level security;

-- ===== Yangi funksiyalar =====
-- Do'stdan kelgan eslatmada jo'natuvchi ismi
alter table public.reminders add column if not exists sender_name text;

-- Do'stga eslatma: havola orqali yuboriladigan eslatmalar
create table if not exists public.shared_reminders (
    token text primary key,
    from_user bigint not null,
    from_name text,
    text text not null,
    remind_at timestamptz not null,
    claimed_by bigint,
    claimed_at timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists shared_from_idx on public.shared_reminders(from_user, claimed_by);
alter table public.shared_reminders enable row level security;

-- Kunlik faol foydalanuvchilar (admin statistikasi uchun)
create table if not exists public.user_activity (
    telegram_id bigint not null,
    day date not null,
    primary key (telegram_id, day)
);
create index if not exists user_activity_day_idx on public.user_activity(day);
alter table public.user_activity enable row level security;

-- ===== 3-yangilanish: takrorlash turlari, oldindan ogohlantirish, ertalabki ro'yxat =====
alter table public.reminders drop constraint if exists reminders_repeat_type_check;
alter table public.reminders add constraint reminders_repeat_type_check
    check (repeat_type in ('once','daily','weekly','weekdays','monthly','interval'));
alter table public.reminders add column if not exists repeat_days text;
alter table public.reminders add column if not exists repeat_every integer;
alter table public.reminders add column if not exists pre_sent boolean not null default false;

alter table public.users add column if not exists pre_minutes integer not null default 0;
alter table public.users add column if not exists digest_hour smallint;
alter table public.users add column if not exists last_digest_date date;
