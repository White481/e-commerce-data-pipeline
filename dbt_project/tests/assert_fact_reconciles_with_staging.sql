-- Reconciliation: ทุกวันที่อยู่ใน fact ต้องมีจำนวนแถวและยอดรวมเท่ากับ staging (เฉพาะแถวที่มีลูกค้า)
-- คืนแถว = test fail

with stg as (
    select invoice_day as date_key, count(*) as row_count, sum(total_amount) as revenue
    from {{ ref('stg_online_retail') }}
    where customer_id is not null
    group by 1
),
fact as (
    select date_key, count(*) as row_count, sum(total_amount) as revenue
    from {{ ref('fact_sales') }}
    group by 1
)
select fact.date_key, fact.row_count, stg.row_count as expected_rows,
       fact.revenue, stg.revenue as expected_revenue
from fact
left join stg using (date_key)
where stg.date_key is null
   or fact.row_count <> stg.row_count
   or fact.revenue <> stg.revenue
