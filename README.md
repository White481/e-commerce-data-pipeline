# E-Commerce Data Engineering Pipeline

End-to-end data pipeline ที่แปลงข้อมูลยอดขายร้านค้าออนไลน์ดิบ (Online Retail dataset, UCI/Kaggle) 
ให้กลายเป็น structured data warehouse พร้อมสำหรับการวิเคราะห์ธุรกิจ

## Architecture
Raw Data (Excel)
↓ [Python + pandas]
Cleansed Data (CSV)
↓ [Python + SQLAlchemy]
PostgreSQL (Docker) — Star Schema
↓ [SQL]
Business Insights


**Stack:** Python, pandas, PostgreSQL 16, Docker, SQLAlchemy, SQL

## Data Model (Star Schema)

- `fact_sales` — ตารางกลาง เก็บ transaction ทุกรายการ
- `dim_customer` — ข้อมูลลูกค้า + ประเทศ
- `dim_product` — ข้อมูลสินค้า
- `dim_date` — ปฏิทิน แยก year/month/day/weekday

เลือกใช้ star schema เพราะเป็นมาตรฐานของ data warehouse ที่ทำให้ query วิเคราะห์ธุรกิจ (revenue, top products) เร็วและอ่านง่าย

## Data Quality Decisions

ระหว่างทำความสะอาดข้อมูล เจอปัญหาข้อมูล 2 จุด ที่ต้องตัดสินใจว่าจะจัดการยังไง:

1. **CustomerID หายไป ~25% ของข้อมูล** — ตัดสินใจ drop ทิ้ง เพราะไม่สามารถวิเคราะห์ per-customer ได้ถ้าไม่รู้ว่าใครซื้อ สมมติฐาน: ระบบขายหน้าร้าน/POS อาจอนุญาตให้ลูกค้าซื้อแบบ guest โดยไม่ login
2. **Quantity ติดลบ (~10,600 แถว)** — ไม่ใช่ error แต่คือ**การคืนสินค้า** เก็บไว้และเพิ่ม flag คอลัมน์ `is_return` แทนการทิ้ง เพื่อให้ยังวิเคราะห์ยอด return แยกได้

## Setup

```bash
# 1. เปิด Postgres container
docker compose up -d

# 2. สร้างตาราง
# รันไฟล์ models/create_tables.sql ผ่าน SQL client (SQLTools/psql)

# 3. ทำความสะอาดข้อมูล
python ingest/clean_data.py

# 4. โหลดข้อมูลเข้า Postgres
python ingest/load_to_postgres.py

# 5. รัน SQL วิเคราะห์ธุรกิจ
# ดูที่ models/analysis_queries.sql
```

## Business Insights

ดูผลลัพธ์เต็มได้ที่ `models/analysis_queries.sql` ครอบคลุม:
- Monthly revenue trend
- Top 10 สินค้าขายดี
- Top 10 ลูกค้าที่ใช้จ่ายสูงสุด
- ยอด return แยกตามเดือน

## Lessons Learned

- Docker volume เก็บ password ไว้ตอนสร้างครั้งแรกเท่านั้น — แก้ `docker-compose.yml` ทีหลังไม่มีผลถ้า volume เดิมยังอยู่ ต้อง `docker compose down -v` เพื่อ recreate
- `pandas.to_sql(if_exists="append")` จะสร้างตารางเองถ้ายังไม่มีอยู่ — อันตรายเพราะจะไม่มี constraint (PK/FK) ตามที่ตั้งใจ ควรแยก schema management (SQL DDL) ออกจาก data loading (Python) ให้ชัดเจน