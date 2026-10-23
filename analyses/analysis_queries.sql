-- 1. Monthly Revenue
SELECT 
    d.year,
    d.month,
    ROUND(SUM(f.total_amount)::numeric, 2) AS monthly_revenue,
    COUNT(DISTINCT f.invoice_no) AS num_orders
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
WHERE f.is_return = false
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

-- 2. Top 10 สินค้าขายดี (ตามรายได้)
SELECT 
    p.description,
    SUM(f.quantity) AS total_quantity_sold,
    ROUND(SUM(f.total_amount)::numeric, 2) AS total_revenue
FROM fact_sales f
JOIN dim_product p ON f.product_key = p.product_key
WHERE f.is_return = false
GROUP BY p.description
ORDER BY total_revenue DESC
LIMIT 10;

-- 3. Top 10 ลูกค้าที่ใช้จ่ายสูงสุด
SELECT 
    c.customer_id,
    c.country,
    ROUND(SUM(f.total_amount)::numeric, 2) AS total_spent,
    COUNT(DISTINCT f.invoice_no) AS num_orders
FROM fact_sales f
JOIN dim_customer c ON f.customer_id = c.customer_id
WHERE f.is_return = false
GROUP BY c.customer_id, c.country
ORDER BY total_spent DESC
LIMIT 10;

-- 4. ยอด Return แยกตามเดือน (โชว์ว่าคิดเรื่อง data quality)
SELECT 
    d.year,
    d.month,
    COUNT(*) AS num_returns,
    ROUND(SUM(ABS(f.total_amount))::numeric, 2) AS return_value
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
WHERE f.is_return = true
GROUP BY d.year, d.month
ORDER BY d.year, d.month;