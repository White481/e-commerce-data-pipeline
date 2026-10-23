-- สร้าง mart ของวัน :day จาก raw.online_retail (รันใน transaction เดียวจาก ingest/run.py)
-- รันซ้ำได้: dim ใช้ ON CONFLICT DO NOTHING, fact ลบของวันนั้นทิ้งแล้วเติมใหม่

INSERT INTO mart.dim_date (date_key, year, month, day, weekday)
SELECT DISTINCT invoice_date::date,
       extract(year FROM invoice_date)::int,
       extract(month FROM invoice_date)::int,
       extract(day FROM invoice_date)::int,
       trim(to_char(invoice_date, 'FMDay'))
FROM raw.online_retail
WHERE invoice_date >= :day AND invoice_date < :next_day
ON CONFLICT (date_key) DO NOTHING;

-- ลูกค้า/สินค้าที่เจอครั้งแรกเป็นตัวกำหนด country/description (เหมือน drop_duplicates เดิม)
INSERT INTO mart.dim_customer (customer_id, country)
SELECT DISTINCT ON (customer_id) customer_id, country
FROM raw.online_retail
WHERE invoice_date >= :day AND invoice_date < :next_day AND customer_id IS NOT NULL
ORDER BY customer_id, invoice_date, line_id
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO mart.dim_product (stock_code, description)
SELECT DISTINCT ON (stock_code) stock_code, description
FROM raw.online_retail
WHERE invoice_date >= :day AND invoice_date < :next_day
ORDER BY stock_code, invoice_date, line_id
ON CONFLICT (stock_code) DO NOTHING;

DELETE FROM mart.fact_sales WHERE date_key = :day;

INSERT INTO mart.fact_sales (
    line_id, invoice_no, product_key, customer_id, date_key,
    quantity, unit_price, total_amount, is_return
)
SELECT r.line_id, r.invoice_no, p.product_key, r.customer_id, r.invoice_date::date,
       r.quantity, r.unit_price, r.quantity * r.unit_price, r.quantity < 0
FROM raw.online_retail r
JOIN mart.dim_product p USING (stock_code)
WHERE r.invoice_date >= :day AND r.invoice_date < :next_day
  AND r.customer_id IS NOT NULL;
