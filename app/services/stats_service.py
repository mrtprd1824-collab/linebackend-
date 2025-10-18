# app/services/stats_service.py - รวมฟังก์ชันคำนวณสถิติรายงานแชท
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from sqlalchemy import text
from sqlalchemy.engine import Result

from app.services.extensions import Session

TZ = pytz.timezone("Asia/Bangkok")


def _parse_iso_datetime(raw: str) -> datetime:
    """แปลงสตริง ISO8601 ให้เป็น datetime ที่มี timezone"""
    cleaned = raw.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = TZ.localize(dt)
    return dt


def resolve_range(
    start_raw: Optional[str],
    end_raw: Optional[str],
) -> Tuple[datetime, datetime]:
    """หาช่วงเวลาแบบ Asia/Bangkok โดย fallback เป็นวันนี้เมื่อไม่ส่ง"""
    now_bkk = datetime.now(TZ)
    default_start = TZ.localize(datetime(now_bkk.year, now_bkk.month, now_bkk.day))
    default_end = default_start + timedelta(days=1)

    if not start_raw or not end_raw:
        return default_start, default_end

    start_dt = _parse_iso_datetime(start_raw).astimezone(TZ)
    end_dt = _parse_iso_datetime(end_raw).astimezone(TZ)

    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(days=1)

    return start_dt, end_dt


def _query_params(start_bkk: datetime, end_bkk: datetime, oa_id: Optional[int]) -> Dict[str, Any]:
    """เตรียม parameter สำหรับ SQL (ใช้ค่า UTC เพื่อเปรียบเทียบในฐานข้อมูล)"""
    start_utc = start_bkk.astimezone(pytz.UTC)
    end_utc = end_bkk.astimezone(pytz.UTC)
    params: Dict[str, Any] = {"start": start_utc, "end": end_utc}
    if oa_id is not None:
        params["oa_id"] = oa_id
    return params


def fetch_summary(
    oa_id: Optional[int],
    start_raw: Optional[str],
    end_raw: Optional[str],
    session=None,
) -> Tuple[Dict[str, Any], Tuple[datetime, datetime]]:
    """ดึง KPI หลักสำหรับสรุปยอดรวม"""
    session = session or Session
    start_bkk, end_bkk = resolve_range(start_raw, end_raw)
    range_params = _query_params(start_bkk, end_bkk, None)

    if oa_id is None:
        # ใช้ ix_line_message_timestamp สำหรับสแกนช่วงเวลารวมทั้งระบบ
        inbound_stmt = text(
            """
            SELECT COUNT(DISTINCT user_id) AS customers_today
            FROM line_message
            WHERE is_outgoing = false
              AND message_type IN ('text','image','sticker')
              AND "timestamp" >= :start
              AND "timestamp" <  :end
            """
        )
        # ใช้ ix_line_message_timestamp สำหรับสแกนทุกข้อความในช่วงเวลา
        active_stmt = text(
            """
            SELECT COUNT(DISTINCT user_id) AS active_customers_today
            FROM line_message
            WHERE message_type IN ('text','image','sticker')
              AND "timestamp" >= :start
              AND "timestamp" <  :end
            """
        )
        # กรณีรวมทั้งระบบจำเป็นต้องสแกนทั้งตาราง (จำนวนเรคอร์ดน้อย)
        blocked_stmt = text(
            """
            SELECT COUNT(*) AS blocked_customers
            FROM line_user
            WHERE is_blocked = true
            """
        )
    else:
        params_with_oa = {**range_params, "oa_id": oa_id}
        # ใช้ idx_line_message_oa_ts_in สำหรับ inbound + เวลา
        inbound_stmt = text(
            """
            SELECT COUNT(DISTINCT user_id) AS customers_today
            FROM line_message
            WHERE is_outgoing = false
              AND message_type IN ('text','image','sticker')
              AND line_account_id = :oa_id
              AND "timestamp" >= :start
              AND "timestamp" <  :end
            """
        )
        # ใช้ idx_line_message_oa_ts สำหรับรวม in/out ตาม OA
        active_stmt = text(
            """
            SELECT COUNT(DISTINCT user_id) AS active_customers_today
            FROM line_message
            WHERE message_type IN ('text','image','sticker')
              AND line_account_id = :oa_id
              AND "timestamp" >= :start
              AND "timestamp" <  :end
            """
        )
        # ใช้ idx_line_user_oa_lastmsg ผ่าน equality บน line_account_id
        blocked_stmt = text(
            """
            SELECT COUNT(*) AS blocked_customers
            FROM line_user
            WHERE is_blocked = true
              AND line_account_id = :oa_id
            """
        )

    inbound_params = range_params if oa_id is None else params_with_oa
    active_params = range_params if oa_id is None else params_with_oa
    blocked_params = {} if oa_id is None else {"oa_id": oa_id}

    inbound_value = session.execute(inbound_stmt, inbound_params).scalar_one()
    active_value = session.execute(active_stmt, active_params).scalar_one()
    blocked_value = session.execute(blocked_stmt, blocked_params).scalar_one()

    kpis = {
        "customers_today": int(inbound_value or 0),
        "active_customers_today": int(active_value or 0),
        "blocked_customers": int(blocked_value or 0),
    }

    return kpis, (start_bkk, end_bkk)


def fetch_by_oa(
    start_raw: Optional[str],
    end_raw: Optional[str],
    session=None,
) -> Tuple[List[Dict[str, Any]], Tuple[datetime, datetime]]:
    """ดึงสถิติแยกตาม OA"""
    session = session or Session
    start_bkk, end_bkk = resolve_range(start_raw, end_raw)
    params = _query_params(start_bkk, end_bkk, oa_id=None)

    # ใช้ idx_line_message_oa_ts_in สำหรับ inbound ตามช่วงเวลา
    stmt = text(
        """
        SELECT lm.line_account_id AS oa_id,
               COALESCE(la.name, '') AS oa_name,
               COUNT(DISTINCT lm.user_id) AS unique_customers_inbound,
               COUNT(*) AS inbound_messages
        FROM line_message AS lm
        LEFT JOIN line_account AS la ON la.id = lm.line_account_id
        WHERE lm.is_outgoing = false
          AND lm.message_type IN ('text','image','sticker')
          AND lm."timestamp" >= :start
          AND lm."timestamp" <  :end
        GROUP BY lm.line_account_id, la.name
        ORDER BY inbound_messages DESC
        """
    )

    result: Result = session.execute(stmt, params)
    rows = [
        {
            "oa_id": row.oa_id,
            "oa_name": row.oa_name or None,
            "unique_customers_inbound": int(row.unique_customers_inbound or 0),
            "inbound_messages": int(row.inbound_messages or 0),
        }
        for row in result
    ]

    return rows, (start_bkk, end_bkk)


def fetch_by_admin(
    oa_id: Optional[int],
    start_raw: Optional[str],
    end_raw: Optional[str],
    session=None,
) -> Tuple[List[Dict[str, Any]], Tuple[datetime, datetime]]:
    """ดึงสถิติแยกตามแอดมิน"""
    session = session or Session
    start_bkk, end_bkk = resolve_range(start_raw, end_raw)
    params = _query_params(start_bkk, end_bkk, oa_id=oa_id)

    if oa_id is None:
        # ใช้ idx_line_message_admin_ts_out (partial) สำหรับกลุ่ม outbound ต่อแอดมิน
        stmt = text(
            """
            SELECT lm.admin_user_id,
                   u.email AS admin_email,
                   COUNT(DISTINCT lm.user_id) AS unique_customers_replied,
                   COUNT(*) AS outbound_messages
            FROM line_message AS lm
            LEFT JOIN "user" AS u ON u.id = lm.admin_user_id
            WHERE lm.is_outgoing = true
              AND lm.admin_user_id IS NOT NULL
              AND lm.message_type IN ('text','image','sticker')
              AND lm."timestamp" >= :start
              AND lm."timestamp" <  :end
            GROUP BY lm.admin_user_id, u.email
            ORDER BY outbound_messages DESC
            """
        )
    else:
        params["oa_id"] = oa_id
        # ใช้ idx_line_message_oa_ts_out ร่วมกับเงื่อนไข admin สำหรับกรองตาม OA
        stmt = text(
            """
            SELECT lm.admin_user_id,
                   u.email AS admin_email,
                   COUNT(DISTINCT lm.user_id) AS unique_customers_replied,
                   COUNT(*) AS outbound_messages
            FROM line_message AS lm
            LEFT JOIN "user" AS u ON u.id = lm.admin_user_id
            WHERE lm.is_outgoing = true
              AND lm.admin_user_id IS NOT NULL
              AND lm.message_type IN ('text','image','sticker')
              AND lm.line_account_id = :oa_id
              AND lm."timestamp" >= :start
              AND lm."timestamp" <  :end
            GROUP BY lm.admin_user_id, u.email
            ORDER BY outbound_messages DESC
            """
        )

    result: Result = session.execute(stmt, params)
    rows = [
        {
            "admin_user_id": row.admin_user_id,
            "admin_email": row.admin_email or None,
            "unique_customers_replied": int(row.unique_customers_replied or 0),
            "outbound_messages": int(row.outbound_messages or 0),
        }
        for row in result
    ]

    return rows, (start_bkk, end_bkk)
