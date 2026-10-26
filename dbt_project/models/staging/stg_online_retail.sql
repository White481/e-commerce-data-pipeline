-- 1 แถวต่อ 1 บรรทัดใน invoice ทำความสะอาดชื่อ/ชนิดคอลัมน์ และเพิ่มคอลัมน์ที่คำนวณได้

select
    line_id,
    invoice_no,
    line_no,
    stock_code,
    description,
    quantity,
    unit_price,
    quantity * unit_price      as total_amount,
    quantity < 0               as is_return,
    invoice_no like 'C%'       as is_cancellation,
    invoice_date,
    invoice_date::date         as invoice_day,
    customer_id,
    country
from {{ source('raw', 'online_retail') }}
