-- Star schema สำหรับวิเคราะห์ สร้างจาก raw.online_retail ด้วย sql/transform_daily.sql
-- Idempotent: รันซ้ำได้

CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS mart.dim_customer (
    customer_id INT PRIMARY KEY,
    country     VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS mart.dim_product (
    product_key SERIAL PRIMARY KEY,
    stock_code  VARCHAR(20) UNIQUE NOT NULL,
    description VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS mart.dim_date (
    date_key DATE PRIMARY KEY,
    year     INT,
    month    INT,
    day      INT,
    weekday  VARCHAR(10)
);

-- grain = 1 บรรทัดใน invoice (เฉพาะแถวที่มี customer_id)
CREATE TABLE IF NOT EXISTS mart.fact_sales (
    line_id      VARCHAR(30) PRIMARY KEY,
    invoice_no   VARCHAR(20) NOT NULL,
    product_key  INT  NOT NULL REFERENCES mart.dim_product(product_key),
    customer_id  INT  NOT NULL REFERENCES mart.dim_customer(customer_id),
    date_key     DATE NOT NULL REFERENCES mart.dim_date(date_key),
    quantity     INT,
    unit_price   NUMERIC(10, 2),
    total_amount NUMERIC(12, 2),
    is_return    BOOLEAN
);

CREATE INDEX IF NOT EXISTS fact_sales_date_key_idx ON mart.fact_sales (date_key);
