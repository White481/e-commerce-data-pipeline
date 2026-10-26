-- product_key = md5(stock_code): คงที่ทุกครั้งที่ build ใหม่ (ต่างจาก SERIAL เดิมที่เปลี่ยนตามลำดับ insert)

select distinct on (stock_code)
    md5(stock_code) as product_key,
    stock_code,
    description
from {{ ref('stg_online_retail') }}
order by stock_code, invoice_date, line_id
