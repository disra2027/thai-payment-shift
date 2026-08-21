"""แปลง raw observations JSON -> ตารางสะอาดใน DuckDB (data/processed/bank.duckdb)

หลักการ clean (และควรเล่าในรายงาน — มันคือของที่ลูกค้าจ่ายเงินซื้อ):
- เก็บทั้งตาราง long (ทุก series รวมกัน) และตาราง wide (พร้อมใช้วิเคราะห์)
- ทุก transformation อธิบายได้ว่าทำไม (คอมเมนต์ที่จุดทำ)
- แถวที่ทิ้ง นับและ log เสมอ ไม่ทิ้งเงียบๆ

schema จริงของ observations ยังไม่เคยเห็น (สเปกบอกแค่ result.series[])
เลยใช้วิธีตรวจจับ key อัตโนมัติ + log สิ่งที่เจอ — ถ้าโครงแปลกจะรู้ทันทีว่าดูตรงไหน
"""

import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "processed" / "bank.duckdb"

# ไฟล์ raw -> ชื่อ metric ในตาราง
SERIES_TABLES = {
    "obs_cheque_volume": "cheque_volume",
    "obs_cheque_value": "cheque_value",
    "obs_mobile_volume": "mobile_volume",
    "obs_mobile_value": "mobile_value",
}


def find_observations(node):
    """หา list ของ observation dict ในโครง result.series[...] โดยไม่ยึดชื่อ key ตายตัว

    บทเรียนจากของจริง: ชั้น series มี key `last_update_date` — heuristic คำว่า "date"
    เลยจับผิดชั้น จึง (1) ถ้ามี key ชื่อ observations ให้เจาะลงก่อนเลย
    (2) จับ record ด้วยคำว่า "period" เท่านั้น (key จริงคือ period_start)"""
    if isinstance(node, dict):
        if isinstance(node.get("observations"), list):
            return node["observations"]
        for v in node.values():
            found = find_observations(v)
            if found:
                return found
    elif isinstance(node, list):
        if node and isinstance(node[0], dict) and any("period" in k.lower() for k in node[0]):
            return node
        for item in node:
            found = find_observations(item)
            if found:
                return found
    return None


def detect_keys(obs: dict) -> tuple[str, str]:
    """เลือก key ที่เป็น period กับ value จาก observation record จริง"""
    period_key = next((k for k in obs if "period" in k.lower()), None)
    value_key = next((k for k in obs if "value" in k.lower()), None)
    if not period_key or not value_key:
        raise SystemExit(f"เดา key ไม่ได้ — keys ที่มีจริง: {list(obs.keys())}\nแก้ detect_keys() ให้ตรง schema นี้")
    return period_key, value_key


def load_series(name: str, metric: str) -> pd.DataFrame:
    files = sorted(RAW_DIR.glob(f"{name}*_*.json"))
    if not files:
        raise FileNotFoundError(f"ไม่มีไฟล์ raw ของ {name} — รัน src/ingest.py ก่อน")
    # รวมทุกไฟล์ (API cap 120 records/request — series ยาวต้องดึงหลายช่วง แล้ว dedupe ตอนท้าย)
    obs = []
    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        found = find_observations(payload["data"])
        if not found:
            raise SystemExit(f"[{name}] หา observations ไม่เจอใน {f.name} — เปิดดูโครงจริง")
        obs.extend(found)

    pk, vk = detect_keys(obs[0])
    print(f"[{name}] {len(obs)} records จาก {len(files)} ไฟล์ | period_key={pk!r} value_key={vk!r}")

    df = pd.DataFrame({"period": [o.get(pk) for o in obs], "value": [o.get(vk) for o in obs]})
    df["metric"] = metric

    # BOT ให้ period เป็น "YYYY-MM" หรือ "YYYY-MM-DD" — to_datetime กินได้ทั้งคู่
    df["period"] = pd.to_datetime(df["period"], errors="coerce")
    # เลขติดคอมมาคือเรื่องปกติของข้อมูลราชการ / ค่าว่างบางงวดก็มี
    df["value"] = pd.to_numeric(df["value"].astype(str).str.replace(",", "").str.strip(), errors="coerce")

    dropped = df["period"].isna() | df["value"].isna()
    if dropped.any():
        print(f"[{name}] ทิ้ง {int(dropped.sum())} แถว (parse ไม่ได้/ค่าว่าง) — เช็ก raw ก่อนเชื่อผลลัพธ์")
    return df.loc[~dropped, ["period", "metric", "value"]].drop_duplicates(subset=["period", "metric"])


if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    frames = [load_series(name, metric) for name, metric in SERIES_TABLES.items()]
    long_df = pd.concat(frames, ignore_index=True).drop_duplicates()

    # wide: หนึ่งแถวต่อเดือน หนึ่งคอลัมน์ต่อ metric — mobile เริ่ม 2017 ช่วงก่อนหน้าเป็น NULL (ตั้งใจ ไม่เติมศูนย์)
    wide_df = long_df.pivot_table(index="period", columns="metric", values="value", aggfunc="first").reset_index()

    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE OR REPLACE TABLE observations_long AS SELECT * FROM long_df")
    con.execute("CREATE OR REPLACE TABLE payments AS SELECT * FROM wide_df")

    print(f"[ok] เขียนลง {DB_PATH}")
    print(con.execute("SELECT min(period) AS first_month, max(period) AS last_month, count(*) AS n_months FROM payments").df())