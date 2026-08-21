"""ดึงข้อมูลจาก BOT API แล้วเก็บ raw JSON ไว้ที่ data/raw/

หลักการ:
- เก็บ raw response เสมอ ห้ามแก้ก่อนเก็บ (audit trail — ถ้า clean พลาด กลับมาทำใหม่ได้)
- แยก ingest ออกจาก clean คนละไฟล์ คนละความรับผิดชอบ

Flow ของ Statistics product (จากสเปกจริงบน portal):
  1. category_list  -> ดู category ทั้งหมด          (ขั้นนี้)
  2. search-series  -> หา series code ใน category    (เปิดหลังรู้ category)
  3. observations   -> ดึงข้อมูลจริงด้วย series code (เปิดหลังรู้ code)
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

load_dotenv()

API_KEY = os.getenv("BOT_API_KEY")
BASE_URL = "https://gateway.api.bot.or.th"  # gateway = ยิง API / portal = หน้าเว็บสมัคร
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# path จากสเปกจริง (แท็บ API specification ของแต่ละ API ใน Statistics product)
DATASETS = {
    # ขั้น 1: ดู category ทั้งหมด — ได้แล้ว (เก็บไว้เผื่อรันซ้ำ)
    "series_catalog": {"path": "/categorylist/category_list/", "params": {}},
    # ขั้น 3: observations — series code จริงจากผลค้น (รายเดือน อัปเดตถึง 2026-05)
    # ดึงตั้งแต่ 2014 ให้เห็นยุคก่อน mobile ด้วย (mobile เริ่มมีข้อมูล 2017-01 — API จะคืนเท่าที่มี)
    # API คืนไม่เกิน 120 observations/request (เจอเองตอนดึงจริง — สเปกไม่ได้บอก)
    # series ยาวกว่า 10 ปีเลยต้องแบ่งสองช่วง clean.py จะรวม+dedupe ให้เอง
    "obs_cheque_volume_p1": {"path": "/observations/", "params": {"series_code": "PSPTFCTHM00061", "start_period": "2014-01-01", "end_period": "2019-12-31", "sort_by": "asc"}},
    "obs_cheque_volume_p2": {"path": "/observations/", "params": {"series_code": "PSPTFCTHM00061", "start_period": "2020-01-01", "end_period": "2026-06-30", "sort_by": "asc"}},
    "obs_cheque_value_p1":  {"path": "/observations/", "params": {"series_code": "PSPTFCTHM00082", "start_period": "2014-01-01", "end_period": "2019-12-31", "sort_by": "asc"}},
    "obs_cheque_value_p2":  {"path": "/observations/", "params": {"series_code": "PSPTFCTHM00082", "start_period": "2020-01-01", "end_period": "2026-06-30", "sort_by": "asc"}},
    "obs_mobile_volume":  {"path": "/observations/", "params": {"series_code": "PSPTFCTHM00222", "start_period": "2014-01-01", "end_period": "2026-06-30", "sort_by": "asc"}},
    "obs_mobile_value":   {"path": "/observations/", "params": {"series_code": "PSPTFCTHM00223", "start_period": "2014-01-01", "end_period": "2026-06-30", "sort_by": "asc"}},
}

# ขั้น 2: หา series code ด้วย keyword (สเปกจริง: GET /search-series/?keyword=...)
# เล็งตาม category ที่เจอในแคตตาล็อก — keyword กว้างไว้ก่อน แล้วค่อยกรองจากผลลัพธ์
# บทเรียนจากรอบแรก: search จับชื่อ series (ไทย+อังกฤษ) ผลไม่เกิน 100 รายการ
# "PromptPay" อังกฤษไม่เจอ — ชื่อ series ใช้คำไทย ลองใหม่ด้วยคำไทย
SEARCH_KEYWORDS = {
    "search_promptpay_th": "พร้อมเพย์",
    "search_province_th": "รายจังหวัด",   # หา FI_CB_011 เงินฝาก-สินเชื่อรายจังหวัด
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=30),
    retry=retry_if_exception_type(requests.RequestException),  # retry เฉพาะ network error
)
def fetch(path: str, params: dict) -> dict:
    resp = requests.get(
        f"{BASE_URL}{path}",
        headers={
            # สเปกระบุ: ใส่ key ดิบใน header Authorization ตรงๆ ไม่มี "Bearer "
            "Authorization": API_KEY,
            "Accept": "application/json",
        },
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        # ไม่ retry — server ตอบแล้วแต่ไม่ใช่ JSON แปลว่า path/auth ผิด ลองซ้ำก็เหมือนเดิม
        raise SystemExit(
            f"API ตอบกลับมาไม่ใช่ JSON (status={resp.status_code})\n"
            f"URL: {resp.url}\n"
            f"500 ตัวแรกของ body:\n{resp.text[:500]}"
        )


def ingest(name: str, path: str, params: dict) -> Path:
    """ดึงหนึ่ง dataset แล้วเก็บ raw JSON พร้อม metadata ว่าดึงเมื่อไหร่"""
    data = fetch(path, params)
    out = RAW_DIR / f"{name}_{date.today().isoformat()}.json"
    out.write_text(
        json.dumps(
            {"fetched_at": date.today().isoformat(), "params": params, "data": data},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[ok] {name} -> {out.name}")
    return out


if __name__ == "__main__":
    if not API_KEY or API_KEY == "your_key_here":
        sys.exit("ยังไม่ได้ใส่ BOT_API_KEY ใน .env — ขอได้ที่ https://portal.api.bot.or.th/")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, spec in DATASETS.items():
        ingest(name, spec["path"], spec["params"])
    for name, keyword in SEARCH_KEYWORDS.items():
        ingest(name, "/search-series/", {"keyword": keyword})