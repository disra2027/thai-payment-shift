"""รันทุก query ใน sql/analysis.sql แล้วพิมพ์ผล — ไม่ต้องลง DuckDB CLI"""
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "data" / "processed" / "bank.duckdb"), read_only=True)
sql = (ROOT / "sql" / "analysis.sql").read_text(encoding="utf-8")

for i, q in enumerate([q.strip() for q in sql.split(";") if q.strip()], 1):
    print(f"\n===== Query {i} =====")
    df = con.execute(q).df()
    if len(df) > 30:  # Q3 ยาวร้อยกว่าเดือน — ดูหัวท้ายพอ ของเต็มอยู่ใน DB
        print(df.head(5).to_string(index=False)); print(f"... ({len(df)} rows) ..."); print(df.tail(5).to_string(index=False))
    else:
        print(df.to_string(index=False))