-- ตาราง payments: หนึ่งแถวต่อเดือน
-- คอลัมน์: period, cheque_volume, cheque_value, mobile_volume, mobile_value
-- (mobile เริ่ม 2017-01 — ก่อนหน้านั้นเป็น NULL ตั้งใจ ไม่เติมศูนย์)

-- *** ข้อควรระวังเรื่องหน่วย — เช็กจาก field unit ใน raw ก่อนเทียบข้าม series ***
-- mobile volume หน่วยเป็น "พันรายการ" ส่วนเช็คต้องดูของจริงว่าหน่วยเดียวกันไหม
-- ถ้าหน่วยต่างกัน การเทียบตัวเลขดิบข้าม series = ผิดทันที ให้เทียบผ่าน index (Q3) แทน
-- นี่คือตัวอย่างจริงของ "ตกลงนิยามก่อนเทียบ" ที่ใช้เล่าให้ลูกค้าฟังได้

-- Q1: ภาพรวมรายปี — เช็คดิ่งเร็วแค่ไหน mobile โตเร็วแค่ไหน
-- หมายเหตุ: ปีล่าสุดเป็นปีไม่เต็ม (ข้อมูลถึง พ.ค.) — YoY ของปีนั้นห้ามอ่านตรงๆ
WITH yearly AS (
    SELECT
        year(period)        AS yr,
        count(*)            AS months_in_year,   -- ไว้ดูว่าปีไหนไม่เต็ม
        sum(cheque_volume)  AS cheque_vol,
        sum(mobile_volume)  AS mobile_vol
    FROM payments
    GROUP BY 1
)
SELECT
    yr,
    months_in_year,
    cheque_vol,
    round(100.0 * (cheque_vol / lag(cheque_vol) OVER (ORDER BY yr) - 1), 2) AS cheque_yoy_pct,
    mobile_vol,
    round(100.0 * (mobile_vol / lag(mobile_vol) OVER (ORDER BY yr) - 1), 2) AS mobile_yoy_pct
FROM yearly
ORDER BY yr;

-- Q2: มูลค่าเฉลี่ยต่อรายการ (หน่วย: บาท) — บอกว่าใครใช้ช่องทางไหนทำอะไร
-- บทเรียนหน่วยของจริง: value=พันล้านบาท volume=พันรายการ → ต้อง x1e6 ให้เป็นบาท/รายการ
-- ไม่งั้น mobile โดนปัดเป็น 0.00 หายทั้งช่องทาง (เจอเองตอนรันรอบแรก)
SELECT
    year(period) AS yr,
    round(1e6 * sum(cheque_value) / nullif(sum(cheque_volume), 0), 0) AS cheque_avg_baht,
    round(1e6 * sum(mobile_value) / nullif(sum(mobile_volume), 0), 0) AS mobile_avg_baht
FROM payments
GROUP BY 1
ORDER BY 1;

-- Q3: เส้นตัดกัน — index เทียบฐานเดือนแรกที่มีครบทั้งคู่ (=100)
-- Index ตัดปัญหาหน่วยต่างกันทิ้งไป เทียบ "อัตราการเปลี่ยนแปลง" ตรงๆ
-- *** แนวโน้มสวนทาง ≠ อันหนึ่งเป็นเหตุของอีกอัน — ในรายงานเขียนแบบนี้เท่านั้น ***
WITH both_present AS (
    SELECT period, cheque_volume, mobile_volume
    FROM payments
    WHERE cheque_volume IS NOT NULL AND mobile_volume IS NOT NULL
),
base AS (
    SELECT cheque_volume AS base_cheque, mobile_volume AS base_mobile
    FROM both_present ORDER BY period LIMIT 1
)
SELECT
    b.period,
    round(100.0 * b.cheque_volume / base.base_cheque, 1) AS cheque_idx,
    round(100.0 * b.mobile_volume / base.base_mobile, 1) AS mobile_idx
FROM both_present b, base
ORDER BY b.period;

-- Q4: เดือนที่มูลค่าธุรกรรม mobile แซงเช็ค (หน่วยเดียวกัน: พันล้านบาท — เทียบตรงได้)
-- ปริมาณรายการ mobile แซงตั้งแต่ก่อนมีข้อมูล แต่ "มูลค่า" คือสนามที่เช็คเคยครอง
WITH flagged AS (
    SELECT period, cheque_value, mobile_value,
           mobile_value > cheque_value AS mobile_ahead
    FROM payments
    WHERE cheque_value IS NOT NULL AND mobile_value IS NOT NULL
)
SELECT period AS crossover_month, cheque_value, mobile_value
FROM flagged
WHERE mobile_ahead
ORDER BY period
LIMIT 3;