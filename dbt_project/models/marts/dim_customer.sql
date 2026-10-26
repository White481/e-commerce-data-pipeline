-- ลูกค้าที่มี customer_id เท่านั้น country = ประเทศที่เจอครั้งแรก (เหมือน drop_duplicates เดิม)

select distinct on (customer_id)
    customer_id,
    country
from {{ ref('stg_online_retail') }}
where customer_id is not null
order by customer_id, invoice_date, line_id
