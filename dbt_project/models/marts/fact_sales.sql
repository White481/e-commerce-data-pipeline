-- grain = 1 บรรทัดใน invoice ที่มี customer_id
-- incremental แบบแทนที่ทั้งวัน (delete+insert ตาม date_key) เหมือน transform เดิม:
--   --vars '{"run_date": "2011-01-05"}'  → สร้างใหม่เฉพาะวันนั้น (ใช้ใน Airflow)
--   ไม่ส่ง run_date                       → ต่อจากวันล่าสุดในตาราง (รวมวันล่าสุดซ้ำ)
--   --full-refresh                        → สร้างใหม่ทั้งหมด

{{ config(
    materialized='incremental',
    unique_key='date_key',
    incremental_strategy='delete+insert',
    on_schema_change='fail',
) }}

select
    s.line_id,
    s.invoice_no,
    md5(s.stock_code)  as product_key,
    s.customer_id,
    s.invoice_day      as date_key,
    s.quantity,
    s.unit_price,
    s.total_amount,
    s.is_return
from {{ ref('stg_online_retail') }} s
where s.customer_id is not null
{% if var('run_date', none) %}
  and s.invoice_day = '{{ var("run_date") }}'::date
{% elif is_incremental() %}
  and s.invoice_day >= (select coalesce(max(date_key), '1900-01-01'::date) from {{ this }})
{% endif %}
