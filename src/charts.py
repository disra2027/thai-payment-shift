"""สร้างกราฟ 2 รูปสำหรับเคส -> data/processed/*.png
ใช้ label อังกฤษ เลี่ยงปัญหาฟอนต์ไทยใน matplotlib บนเครื่องที่ไม่ได้ตั้งค่า"""
from pathlib import Path
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "charts"  # อยู่นอก data/ เพราะต้อง commit ให้ README บน GitHub เห็น
OUT.mkdir(exist_ok=True)
con = duckdb.connect(str(ROOT / "data" / "processed" / "bank.duckdb"), read_only=True)

df = con.execute("SELECT * FROM payments ORDER BY period").df()

# ---- Chart 1: มูลค่าเช็ค vs mobile (หน่วยเดียวกัน เทียบตรงได้) + จุดตัด ก.ค. 2020 ----
fig, ax = plt.subplots(figsize=(10, 5.5))
ax.plot(df["period"], df["cheque_value"], label="Cheque", linewidth=2)
ax.plot(df["period"], df["mobile_value"], label="Mobile banking", linewidth=2)
cross = df[(df["mobile_value"] > df["cheque_value"]) & df["cheque_value"].notna()].iloc[0]
ax.axvline(cross["period"], linestyle="--", alpha=0.6, color="gray")
ax.annotate("Jul 2020\nmobile overtakes cheque", xy=(cross["period"], cross["mobile_value"]),
            xytext=(15, 30), textcoords="offset points", fontsize=9)
ax.set_title("Value of payments: cheque vs mobile banking (THB billions/month)")
ax.set_ylabel("THB billions")
ax.legend()
fig.tight_layout()
fig.savefig(OUT / "chart1_value_crossover.png", dpi=150)
print("saved chart1_value_crossover.png")

# ---- Chart 2: มูลค่าเฉลี่ยต่อรายการ (log scale — สองเส้นห่างกัน ~300 เท่า) ----
avg = con.execute("""
    SELECT year(period) AS yr,
           1e6 * sum(cheque_value) / nullif(sum(cheque_volume),0) AS cheque_avg,
           1e6 * sum(mobile_value) / nullif(sum(mobile_volume),0) AS mobile_avg
    FROM payments GROUP BY 1 HAVING count(*) = 12 ORDER BY 1
""").df()  # HAVING count(*)=12 ตัดปีไม่เต็มทิ้ง — กันกราฟโกหก
fig, ax = plt.subplots(figsize=(10, 5.5))
ax.plot(avg["yr"], avg["cheque_avg"], marker="o", label="Cheque (avg THB/txn)")
ax.plot(avg["yr"], avg["mobile_avg"], marker="o", label="Mobile (avg THB/txn)")
ax.set_yscale("log")
ax.set_title("Average value per transaction (log scale) - two different worlds")
ax.set_ylabel("THB per transaction (log)")
ax.legend()
ax.grid(True, which="both", alpha=0.3)
fig.tight_layout()
fig.savefig(OUT / "chart2_avg_ticket.png", dpi=150)
print("saved chart2_avg_ticket.png")