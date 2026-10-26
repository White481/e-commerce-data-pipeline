-- เทียบ dbt fact กับ fact_sales เดิม (public.fact_sales จาก Phase 0: clean_data.py + load_to_postgres.py)
-- รัน: dbt compile แล้วเอา SQL ใน target/compiled/.../reconcile_with_legacy.sql ไปรันใน psql

with legacy as (
    select count(*) as row_count, sum(total_amount) as revenue,
           count(*) filter (where unit_price <= 0) as zero_price_rows
    from public.fact_sales
),
dbt as (
    select count(*) as row_count, sum(total_amount) as revenue,
           count(*) filter (where unit_price <= 0) as zero_price_rows
    from {{ ref('fact_sales') }}
)
select 'legacy' as source, * from legacy
union all
select 'dbt', * from dbt
