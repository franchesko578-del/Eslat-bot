"""Sozlamalar: barcha maxfiy ma'lumotlar muhit o'zgaruvchilaridan o'qiladi."""
import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Kompyuterda .env faylidan o'qiydi. Render'da bu fayl kerak emas.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    supabase_url: str
    supabase_key: str
    admin_id: int
    timezone_name: str
    tz: ZoneInfo
    port: int
    check_interval: int
    max_reminders: int


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} sozlanmagan! Render'dagi Environment bo'limini "
            f"yoki .env faylini tekshiring."
        )
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} butun son bo'lishi kerak, hozir: {raw!r}")


def load_settings() -> Settings:
    tz_name = os.getenv("TIMEZONE", "").strip() or "Asia/Tashkent"
    return Settings(
        bot_token=_required("BOT_TOKEN"),
        supabase_url=_required("SUPABASE_URL").rstrip("/"),
        supabase_key=_required("SUPABASE_SERVICE_KEY"),
        admin_id=_int("ADMIN_ID", 7507192517),
        timezone_name=tz_name,
        tz=ZoneInfo(tz_name),
        port=_int("PORT", 10000),
        check_interval=max(5, _int("CHECK_INTERVAL", 10)),
        max_reminders=max(1, _int("MAX_REMINDERS_PER_USER", 100)),
    )
