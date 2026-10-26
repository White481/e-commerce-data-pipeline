{#- ใช้ชื่อ schema ตรง ๆ (staging, marts) แทนค่า default ของ dbt ที่จะได้ analytics_staging -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name else target.schema }}
{%- endmacro %}
