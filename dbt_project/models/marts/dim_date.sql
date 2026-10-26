select distinct
    invoice_day                              as date_key,
    extract(year from invoice_day)::int      as year,
    extract(month from invoice_day)::int     as month,
    extract(day from invoice_day)::int       as day,
    trim(to_char(invoice_day, 'FMDay'))      as weekday
from {{ ref('stg_online_retail') }}
