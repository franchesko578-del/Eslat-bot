"""Supabase (PostgREST) bilan ishlash. Qo'shimcha kutubxona kerak emas."""
import asyncio
import json as jsonlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import aiohttp

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Baza bilan ishlashda xatolik."""


def iso_z(dt: datetime) -> str:
    """Vaqtni '2026-11-05T09:00:00Z' (UTC) ko'rinishiga o'tkazadi."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value: str) -> datetime:
    """Bazadan kelgan vaqt matnini datetime'ga aylantiradi."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_registered(user: Optional[dict]) -> bool:
    """To'liq ro'yxatdan o'tgan: rozilik berilgan va telefon yuborilgan."""
    return bool(user and user.get("consent") and user.get("phone"))


def _total(headers) -> int:
    content_range = headers.get("Content-Range", "")
    if "/" in content_range:
        tail = content_range.split("/")[-1]
        if tail.isdigit():
            return int(tail)
    return 0


class Database:
    def __init__(self, url: str, key: str) -> None:
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self._headers = {"apikey": key, "Content-Type": "application/json"}
        # Eski (JWT) kalitlar uchun Authorization sarlavhasi ham kerak
        if key.startswith("eyJ"):
            self._headers["Authorization"] = f"Bearer {key}"
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        timeout = aiohttp.ClientTimeout(total=20)
        self._session = aiohttp.ClientSession(
            timeout=timeout, headers=self._headers
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: Optional[dict] = None,
        body: Any = None,
        prefer: Optional[str] = None,
        retries: int = 0,
    ):
        url = f"{self.base_url}/{table}"
        headers = {"Prefer": prefer} if prefer else {}
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                async with self._session.request(
                    method, url, params=params, json=body, headers=headers
                ) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        raise DatabaseError(
                            f"{method} {table} -> {resp.status}: {text[:300]}"
                        )
                    data = jsonlib.loads(text) if text else None
                    return data, resp.headers
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                last_error = error
                logger.warning(
                    "Baza so'rovi muvaffaqiyatsiz (%s %s): %r",
                    method,
                    table,
                    error,
                )
                if attempt < retries:
                    await asyncio.sleep(1 + attempt)
        raise DatabaseError(f"Bazaga ulanib bo'lmadi: {last_error!r}")

    async def _count(self, table: str, column: str, filters: dict) -> int:
        params = dict(filters)
        params["select"] = column
        params["limit"] = "1"
        _, headers = await self._request(
            "GET", table, params=params, prefer="count=exact", retries=1
        )
        return _total(headers)

    # ---------- Ulanishni tekshirish ----------
    async def ping(self) -> None:
        await self._request(
            "GET", "reminders", params={"select": "id", "limit": "1"}, retries=2
        )
        await self._request(
            "GET", "users", params={"select": "telegram_id", "limit": "1"}
        )

    # ---------- Foydalanuvchilar ----------
    async def upsert_user(
        self, user_id: int, full_name: str, username: Optional[str]
    ) -> None:
        body = {
            "telegram_id": user_id,
            "full_name": full_name,
            "username": username,
            "last_seen_at": iso_z(datetime.now(timezone.utc)),
        }
        await self._request(
            "POST",
            "users",
            params={"on_conflict": "telegram_id"},
            body=body,
            prefer="resolution=merge-duplicates,return=minimal",
            retries=1,
        )

    async def user_ids(self, offset: int, limit: int) -> list:
        data, _ = await self._request(
            "GET",
            "users",
            params={
                "select": "telegram_id",
                "order": "telegram_id.asc",
                "limit": str(limit),
                "offset": str(offset),
            },
            retries=1,
        )
        return [row["telegram_id"] for row in (data or [])]

    # ---------- Ro'yxatdan o'tish, xavfsizlik va admin ----------
    async def get_user(self, user_id: int):
        data, _ = await self._request("GET", "users", params={"select": "*", "telegram_id": f"eq.{user_id}", "limit": "1"}, retries=1)
        return data[0] if data else None

    async def register_user(self, user_id: int, full_name: str, username: Optional[str], phone: str):
        body = {"telegram_id": user_id, "full_name": full_name, "username": username, "phone": phone,
                "consent": True, "consent_at": iso_z(datetime.now(timezone.utc)),
                "last_seen_at": iso_z(datetime.now(timezone.utc))}
        await self._request("POST", "users", params={"on_conflict": "telegram_id"}, body=body,
                            prefer="resolution=merge-duplicates,return=minimal", retries=1)

    async def is_blocked(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return bool(user and user.get("is_blocked"))

    async def set_blocked(self, user_id: int, blocked: bool):
        await self._request("PATCH", "users", params={"telegram_id": f"eq.{user_id}"},
            body={"is_blocked": blocked}, prefer="return=minimal")

    async def list_users(self, offset: int, limit: int):
        data, headers = await self._request("GET", "users", params={"select": "telegram_id,full_name,username,phone,is_blocked,created_at", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}, prefer="count=exact", retries=1)
        return data or [], _total(headers)

    async def log_message(self, user_id: int, direction: str, message_type: str, content: str):
        await self._request("POST", "message_logs", body={"telegram_id": user_id, "direction": direction, "message_type": message_type, "content": content[:4000]}, prefer="return=minimal")

    async def get_message_logs(self, user_id: int, limit: int = 20):
        data, _ = await self._request("GET", "message_logs", params={"select": "direction,message_type,content,created_at", "telegram_id": f"eq.{user_id}", "order": "created_at.desc", "limit": str(limit)}, retries=1)
        return data or []

    async def list_channels(self):
        data, _ = await self._request("GET", "required_channels", params={"select": "id,chat_id,title,invite_link", "order": "id.asc"}, retries=1)
        return data or []

    async def add_channel(self, chat_id: str, title: str, invite_link: Optional[str] = None):
        await self._request("POST", "required_channels", body={"chat_id": chat_id, "title": title, "invite_link": invite_link}, prefer="return=minimal")

    async def remove_channel(self, channel_id: int):
        await self._request("DELETE", "required_channels", params={"id": f"eq.{channel_id}"}, prefer="return=minimal")

    async def update_user(self, user_id: int, fields: dict) -> None:
        await self._request(
            "PATCH",
            "users",
            params={"telegram_id": f"eq.{user_id}"},
            body=fields,
            prefer="return=minimal",
        )

    async def users_with_pre(self) -> list:
        """Oldindan ogohlantirish yoqilgan foydalanuvchilar."""
        data, _ = await self._request(
            "GET",
            "users",
            params={
                "select": "telegram_id,pre_minutes",
                "pre_minutes": "gt.0",
                "is_blocked": "eq.false",
                "limit": "5000",
            },
            retries=1,
        )
        return data or []

    async def users_with_digest(self) -> list:
        """Ertalabki ro'yxat yoqilgan foydalanuvchilar."""
        data, _ = await self._request(
            "GET",
            "users",
            params={
                "select": "telegram_id,digest_hour,last_digest_date",
                "digest_hour": "not.is.null",
                "is_blocked": "eq.false",
                "limit": "5000",
            },
            retries=1,
        )
        return data or []

    # ---------- Eslatmalar ----------
    async def create_reminders(self, rows: list) -> list:
        data, _ = await self._request(
            "POST",
            "reminders",
            body=rows,
            prefer="return=representation",
        )
        return data or []

    async def count_active(self, user_id: int) -> int:
        return await self._count(
            "reminders",
            "id",
            {"user_id": f"eq.{user_id}", "status": "eq.active"},
        )

    async def list_active(self, user_id: int, offset: int, limit: int):
        params = {
            "select": "*",
            "user_id": f"eq.{user_id}",
            "status": "eq.active",
            "order": "remind_at.asc,id.asc",
            "limit": str(limit),
            "offset": str(offset),
        }
        data, headers = await self._request(
            "GET", "reminders", params=params, prefer="count=exact", retries=1
        )
        return (data or []), _total(headers)

    async def get_reminder(self, reminder_id: int, user_id: int):
        params = {
            "select": "*",
            "id": f"eq.{reminder_id}",
            "user_id": f"eq.{user_id}",
            "status": "eq.active",
            "limit": "1",
        }
        data, _ = await self._request(
            "GET", "reminders", params=params, retries=1
        )
        return data[0] if data else None

    async def get_reminder_any(self, reminder_id: int, user_id: int):
        """Holatidan qat'i nazar (faol, bajarilgan) eslatmani o'qiydi."""
        params = {
            "select": "*",
            "id": f"eq.{reminder_id}",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        }
        data, _ = await self._request("GET", "reminders", params=params, retries=1)
        return data[0] if data else None

    async def update_reminder(
        self, reminder_id: int, user_id: int, fields: dict
    ) -> bool:
        params = {"id": f"eq.{reminder_id}", "user_id": f"eq.{user_id}"}
        data, _ = await self._request(
            "PATCH",
            "reminders",
            params=params,
            body=fields,
            prefer="return=representation",
        )
        return bool(data)

    async def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        params = {"id": f"eq.{reminder_id}", "user_id": f"eq.{user_id}"}
        data, _ = await self._request(
            "DELETE",
            "reminders",
            params=params,
            prefer="return=representation",
        )
        return bool(data)

    async def delete_all_active(self, user_id: int) -> int:
        params = {"user_id": f"eq.{user_id}", "status": "eq.active"}
        data, _ = await self._request(
            "DELETE",
            "reminders",
            params=params,
            prefer="return=representation",
        )
        return len(data or [])

    # ---------- Rejalovchi uchun ----------
    async def due_reminders(self, now: datetime, limit: int) -> list:
        params = {
            "select": "*",
            "status": "eq.active",
            "remind_at": f"lte.{iso_z(now)}",
            "order": "remind_at.asc,id.asc",
            "limit": str(limit),
        }
        data, _ = await self._request(
            "GET", "reminders", params=params, retries=1
        )
        return data or []

    async def pre_candidates(
        self, user_ids: list, now: datetime, until: datetime
    ) -> list:
        """Oldindan ogohlantirish yuborilishi mumkin bo'lgan eslatmalar."""
        result = []
        for i in range(0, len(user_ids), 150):
            chunk = user_ids[i : i + 150]
            params = {
                "select": "*",
                "status": "eq.active",
                "pre_sent": "eq.false",
                "user_id": f"in.({','.join(str(u) for u in chunk)})",
                "and": f"(remind_at.gt.{iso_z(now)},remind_at.lte.{iso_z(until)})",
                "order": "remind_at.asc",
                "limit": "200",
            }
            data, _ = await self._request("GET", "reminders", params=params, retries=1)
            result.extend(data or [])
        return result

    async def mark_pre_sent(self, reminder_id: int) -> None:
        await self._request(
            "PATCH",
            "reminders",
            params={"id": f"eq.{reminder_id}"},
            body={"pre_sent": True},
            prefer="return=minimal",
        )

    async def reminders_between(
        self, user_id: int, start: datetime, end: datetime, limit: int = 30
    ) -> list:
        params = {
            "select": "text,remind_at,repeat_type,repeat_days,repeat_every",
            "user_id": f"eq.{user_id}",
            "status": "eq.active",
            "and": f"(remind_at.gte.{iso_z(start)},remind_at.lt.{iso_z(end)})",
            "order": "remind_at.asc",
            "limit": str(limit),
        }
        data, _ = await self._request("GET", "reminders", params=params, retries=1)
        return data or []

    async def claim(
        self,
        reminder_id: int,
        old_time: datetime,
        new_time: Optional[datetime],
    ) -> bool:
        """Eslatmani 'band qiladi'. Faqat bitta jarayon muvaffaqiyatli bo'ladi,
        shuning uchun bir eslatma ikki marta yuborilmaydi."""
        params = {
            "id": f"eq.{reminder_id}",
            "status": "eq.active",
            "remind_at": f"eq.{iso_z(old_time)}",
        }
        if new_time is None:
            body = {"status": "done"}
        else:
            body = {"remind_at": iso_z(new_time), "pre_sent": False}
        data, _ = await self._request(
            "PATCH",
            "reminders",
            params=params,
            body=body,
            prefer="return=representation",
        )
        return bool(data)

    async def revert(
        self,
        reminder_id: int,
        old_time: datetime,
        fail_count: int,
        give_up: bool,
    ) -> None:
        body = {
            "remind_at": iso_z(old_time),
            "status": "failed" if give_up else "active",
            "fail_count": fail_count,
        }
        await self._request(
            "PATCH",
            "reminders",
            params={"id": f"eq.{reminder_id}"},
            body=body,
            prefer="return=minimal",
        )

    async def set_status(self, reminder_id: int, status: str) -> None:
        await self._request(
            "PATCH",
            "reminders",
            params={"id": f"eq.{reminder_id}"},
            body={"status": status},
            prefer="return=minimal",
        )

    async def add_log(
        self,
        reminder_id: int,
        user_id: int,
        ok: bool,
        error: Optional[str] = None,
    ) -> None:
        body = {
            "reminder_id": reminder_id,
            "user_id": user_id,
            "ok": ok,
            "error": error[:300] if error else None,
        }
        await self._request(
            "POST", "reminder_logs", body=body, prefer="return=minimal"
        )

    # ---------- Do'stga eslatma (havola) ----------
    async def create_share(self, row: dict) -> dict:
        data, _ = await self._request(
            "POST", "shared_reminders", body=row, prefer="return=representation"
        )
        return data[0]

    async def count_open_shares(self, user_id: int) -> int:
        return await self._count(
            "shared_reminders",
            "token",
            {"from_user": f"eq.{user_id}", "claimed_by": "is.null"},
        )

    async def get_share(self, token: str):
        data, _ = await self._request(
            "GET",
            "shared_reminders",
            params={"select": "*", "token": f"eq.{token}", "limit": "1"},
            retries=1,
        )
        return data[0] if data else None

    async def claim_share(self, token: str, user_id: int) -> bool:
        """Havolani band qiladi. Faqat birinchi odam muvaffaqiyatli bo'ladi."""
        data, _ = await self._request(
            "PATCH",
            "shared_reminders",
            params={"token": f"eq.{token}", "claimed_by": "is.null"},
            body={
                "claimed_by": user_id,
                "claimed_at": iso_z(datetime.now(timezone.utc)),
            },
            prefer="return=representation",
        )
        return bool(data)

    async def unclaim_share(self, token: str) -> None:
        await self._request(
            "PATCH",
            "shared_reminders",
            params={"token": f"eq.{token}"},
            body={"claimed_by": None, "claimed_at": None},
            prefer="return=minimal",
        )

    # ---------- Kunlik faollik ----------
    async def touch_activity(self, user_id: int, day: date) -> None:
        """Foydalanuvchi shu kuni faol bo'lganini yozadi (kuniga bir marta)."""
        await self._request(
            "POST",
            "user_activity",
            params={"on_conflict": "telegram_id,day"},
            body={"telegram_id": user_id, "day": day.isoformat()},
            prefer="resolution=ignore-duplicates,return=minimal",
        )

    async def daily_stats(self, tz: ZoneInfo, days: int = 7) -> list:
        """Oxirgi kunlar bo'yicha: faol, yangi, yaratilgan, yuborilgan."""
        today = datetime.now(tz).date()

        async def one(d: date) -> dict:
            start = datetime.combine(d, time.min, tzinfo=tz).astimezone(timezone.utc)
            end = datetime.combine(
                d + timedelta(days=1), time.min, tzinfo=tz
            ).astimezone(timezone.utc)

            def rng(col: str) -> dict:
                return {"and": f"({col}.gte.{iso_z(start)},{col}.lt.{iso_z(end)})"}

            active, new, created, sent = await asyncio.gather(
                self._count("user_activity", "telegram_id", {"day": f"eq.{d.isoformat()}"}),
                self._count("users", "telegram_id", rng("created_at")),
                self._count("reminders", "id", rng("created_at")),
                self._count("reminder_logs", "id", {"ok": "eq.true", **rng("sent_at")}),
            )
            return {
                "day": d,
                "active": active,
                "new": new,
                "created": created,
                "sent": sent,
            }

        return list(
            await asyncio.gather(
                *(one(today - timedelta(days=i)) for i in range(days))
            )
        )

    # ---------- Admin statistikasi ----------
    async def stats(self, day_start: datetime) -> dict:
        since = f"gte.{iso_z(day_start)}"
        (
            users_total,
            users_today,
            active,
            reminders_total,
            sent_total,
            sent_today,
            failed_total,
        ) = await asyncio.gather(
            self._count("users", "telegram_id", {}),
            self._count("users", "telegram_id", {"created_at": since}),
            self._count("reminders", "id", {"status": "eq.active"}),
            self._count("reminders", "id", {}),
            self._count("reminder_logs", "id", {"ok": "eq.true"}),
            self._count(
                "reminder_logs", "id", {"ok": "eq.true", "sent_at": since}
            ),
            self._count("reminder_logs", "id", {"ok": "eq.false"}),
        )
        return {
            "users_total": users_total,
            "users_today": users_today,
            "active": active,
            "reminders_total": reminders_total,
            "sent_total": sent_total,
            "sent_today": sent_today,
            "failed_total": failed_total,
        }
