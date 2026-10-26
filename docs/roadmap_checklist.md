# E-commerce Pipeline Roadmap

## สถานะตอนนี้

ทำครบทุก phase แล้ว Phase 0–7 และ 9 อยู่ใน `main` (Phase 8 เป็นทางเลือก ไม่ได้ทำ) เหลือแค่ฝึกตอบคำถามสัมภาษณ์ ลำดับทำงานตาม roadmap คือ 0 → 1 → 2 → 3 → 5 → 4 → 6 → 7 → 9 (Airflow มาก่อน dbt เพราะ dbt ต้องเสียบเข้า DAG)

| Phase | เรื่อง | Status | PR |
| --- | --- | --- | --- |
| 0 | วางรากฐาน | Merged | #1 |
| 1 | โหลดซ้ำได้ + บันทึก audit | Merged | #2 |
| 2 | คุณภาพข้อมูล | Merged | #3 |
| 3 | โหลดทีละวัน | Merged | #4 |
| 5 | Airflow | Merged | #5 |
| 4 | dbt | Merged | #6 |
| 6 | CI | Merged | #7 |
| 7 | Dashboard Metabase + สิทธิ์อ่านอย่างเดียว | Merged | #8 |
| 9 | README + เรซูเม่ | Merged | #9 |

**ทำต่อทันที**

- [x] Merge PR ของ Phase 1–7 เข้า `main`
- [x] Merge PR ของ Phase 9
- [ ] ฝึกตอบคำถามใน `docs/interview_prep.md`

## Phase 0: วางรากฐาน

- [x] ย้าย credentials ไป `.env` และมี `.env.example`
- [x] เปลี่ยนรหัสผ่าน Postgres (รหัสเก่าหลุดอยู่ใน git history)
- [x] `requirements.txt`, `Makefile`, `.gitignore`, `pyproject.toml`
- [x] venv ใหม่เป็น Python 3.14 และเอา `venv/` ออกจาก git
- [x] unit test ชุดแรก (`make test`, `make lint`)
- [x] รัน pipeline ครบกับ Postgres จริง
- [x] เปิด `NOTES.md` จดปัญหาที่เจอ

## Phase 1: โหลดซ้ำได้ + บันทึก audit

- [x] เช็ก grain: คู่ invoice_no + stock_code ซ้ำ 9,694 คู่ (จดตัวเลขไว้ใน NOTES.md)
- [x] สร้าง `line_id` = invoice_no + เลขบรรทัดภายใน invoice
- [x] `sql/init.sql` มี schema raw และ audit รวม 3 ตาราง
- [x] `ingest/load_raw.py` โหลดเข้า temp table แล้ว `INSERT ... ON CONFLICT` ใน transaction เดียว
- [x] ทุกครั้งที่รัน เขียน 1 แถวลง `audit.pipeline_runs`
- [x] `tests/test_load_idempotent.py` รัน 2 รอบแล้ว count เท่าเดิม
- [x] ลบข้อมูลบางส่วนแล้วรันใหม่ ได้กลับมาครบ (insert กลับมา 10,098 แถว)

**คำถามที่ต้องตอบได้ด้วยคำพูดตัวเอง**

- [ ] idempotency คืออะไร
- [ ] grain ของ fact คืออะไร
- [ ] ทำไมต้องใช้ transaction

## Phase 2: คุณภาพข้อมูล

- [x] ติดตั้ง pandera และเขียน schema ไว้ใน `ingest/validate.py`
- [x] แยกแถวดีกับแถวเสีย แถวเสียเขียนลง `audit.rejected_rows` พร้อมเหตุผล
- [x] circuit breaker: แถวเสียเกิน 5% ให้ raise error
- [x] unit test 4 กรณี: price ≤ 0, invoice C ที่ quantity เป็นบวก, วันที่ว่าง, line_id ซ้ำ
- [x] ทุก batch พิมพ์สรุปจำนวนแถวที่อ่าน ปฏิเสธ และโหลด
- [x] ตัดสินใจเรื่อง CustomerID และเขียนเหตุผลลง README แล้ว: เก็บไว้ที่เดิม ไม่ย้ายเข้า validate
- [x] ตัดสินใจเรื่อง 5,268 แถวที่ซ้ำกันทุกคอลัมน์: เก็บไว้ทั้งหมด (อาจเป็นการสแกนซ้ำจริง) และเขียนไว้ใน README หัวข้อ Limitations

## Phase 3: โหลดทีละวัน

- [x] `ingest/split_batches.py` แบ่งเป็นไฟล์รายวันใน `data/landing/`
- [x] `ingest/run.py` รองรับ `load --date YYYY-MM-DD` และ `load --since-last`
- [x] วันที่ไม่มีไฟล์บันทึกเป็น skipped แล้วจบโดยไม่ error
- [x] `--since-last` โหลดวัน watermark ซ้ำอีกรอบ
- [x] โหลด 5 วันแล้วรันซ้ำ ได้ count เท่าเดิม (13,963 แถว)
- [x] ลบ 3 วันท้ายแล้วรัน `--since-last` ข้อมูลตามทันเอง
- [x] แก้บั๊ก 2 ตัว: override ที่อนุมัติแล้วไม่ถูกจำไว้ และ watermark กระโดดข้าม 22 วัน

## Phase 5: จัดการ pipeline ด้วย Airflow

- [x] เพิ่ม Airflow แบบ standalone ใน `docker-compose.yml` และ pin version ไว้ที่ 3.3.2
- [x] `dags/ecommerce_daily.py` รัน setup → ingest → transform → notify
- [x] ตั้ง `catchup=True`, `retries=2`, `max_active_runs=1`
- [x] backfill 1 เดือนแล้วแคปภาพ Graph view ใส่ README
- [x] จงใจทำให้ task ล้มกลางทาง แล้ว clear และรันใหม่ ข้อมูลไม่ซ้ำ (วัน 2011-01-05 ยังมี 1,117 แถว)
- [x] วันที่ไม่มีข้อมูลไม่ทำให้ DAG แดง
- [ ] ปิด toggle ของ DAG ใน UI ทุกครั้งที่เปิด Airflow ใหม่ ถ้าไม่อยากให้ catchup วิ่งต่อ

## Phase 4: แปลงข้อมูลด้วย dbt

- [x] ติดตั้ง dbt-core 1.12.6 + dbt-postgres 1.11.0 และ `dbt init`
- [x] `profiles.yml` อ่านค่าเชื่อมต่อจาก env (`dbt debug` ผ่าน)
- [x] เขียน `stg_online_retail` → `dim_customer`, `dim_product`, `dim_date`, `fact_sales` (incremental)
- [x] เขียน tests: unique, not_null, relationships, accepted_values
- [x] `dbt build` ผ่านครบ
- [x] Reconciliation: เทียบยอดรวม total_amount และจำนวนแถวกับตารางเดิม และอธิบายส่วนต่าง
- [x] แคปภาพ lineage graph (`dbt docs generate` + `dbt docs serve`)
- [x] เปลี่ยน task transform ใน DAG เป็น `dbt build`
- [x] เปิด PR ของ Phase 4

## Phase 6: CI ตรวจโค้ดอัตโนมัติ

- [x] สร้าง `.github/workflows/ci.yml` จาก roadmap
- [x] push แล้วขึ้นเครื่องหมายเขียว
- [x] ใส่ badge ใน README

## Phase 7: Dashboard Metabase + สิทธิ์อ่านอย่างเดียว

- [x] เพิ่ม Metabase ใน `docker-compose.yml`
- [x] สร้าง role อ่านอย่างเดียวที่ทำได้แค่ SELECT บน schema marts (ใช้ชื่อ `metabase_ro` เพราะ `analyst_ro` เป็นของ agent)
- [x] กราฟรายได้รายเดือน
- [x] กราฟสินค้าขายดี
- [x] กราฟประเทศที่ขายได้มากที่สุด
- [x] กราฟอัตราการคืนสินค้า (return rate)
- [x] กราฟลูกค้าที่กลับมาซื้อซ้ำ (repeat customer)

## Phase 9: README + เรซูเม่

ตัวเลขจริงที่ใช้ได้แล้ว: 541,909 แถวดิบ, ปฏิเสธ 0.46%, โหลดทีละวัน 305 วัน, backfill 31 วัน

- [x] เขียน README ตามโครง 9 หัวข้อใน roadmap
- [x] ส่วน What I ran into (ดึงจาก NOTES.md)
- [x] ส่วน Limitations (เช่น line_id ขึ้นกับลำดับแถวในไฟล์ต้นทาง)
- [x] เขียน resume bullet ด้วยตัวเลขจริง
- [ ] ฝึกตอบคำถาม 10 ข้อด้วยคำพูดตัวเอง (`docs/interview_prep.md`)
