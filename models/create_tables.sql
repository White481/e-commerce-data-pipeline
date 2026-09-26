-- Dimension: ลูกค้า
CREATE TABLE dim_customer (
    customer_id INT PRIMARY KEY,
    country VARCHAR(100)
);

-- Dimension: สินค้า
CREATE TABLE dim_product (
    product_key SERIAL PRIMARY KEY,
    stock_code VARCHAR(20) UNIQUE NOT NULL,
    description VARCHAR(255)
);

-- Dimension: วันที่
CREATE TABLE dim_date (
    date_key DATE PRIMARY KEY,
    year INT,
    month INT,
    day INT,
    weekday VARCHAR(10)
);

-- Fact: ยอดขาย
CREATE TABLE fact_sales (
    invoice_no VARCHAR(20),
    product_key INT REFERENCES dim_product(product_key),
    customer_id INT REFERENCES dim_customer(customer_id),
    date_key DATE REFERENCES dim_date(date_key),
    quantity INT,
    unit_price NUMERIC(10, 2),
    total_amount NUMERIC(12, 2),
    is_return BOOLEAN
);