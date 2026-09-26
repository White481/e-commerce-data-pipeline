import pandas as pd
from sqlalchemy import create_engine

# 1. เชื่อมต่อ Postgres (ค่าตรงกับ docker-compose.yml)
engine = create_engine("postgresql://white:Peerawhite14@localhost:5432/ecommerce")

# 2. โหลดข้อมูลที่ clean แล้ว
df = pd.read_csv("data/cleaned_online_retail.csv")
print(f"โหลดข้อมูล: {df.shape[0]} แถว")

# 3. เตรียม dim_customer (unique customer + country)
dim_customer = df[["CustomerID", "Country"]].drop_duplicates(subset=["CustomerID"])
dim_customer.columns = ["customer_id", "country"]
dim_customer.to_sql("dim_customer", engine, if_exists="append", index=False)
print(f"insert dim_customer: {len(dim_customer)} แถว")

# 4. เตรียม dim_product (unique stock_code + description)
dim_product = df[["StockCode", "Description"]].drop_duplicates(subset=["StockCode"])
dim_product.columns = ["stock_code", "description"]
dim_product.to_sql("dim_product", engine, if_exists="append", index=False)
print(f"insert dim_product: {len(dim_product)} แถว")

# 5. เตรียม dim_date (unique date จาก InvoiceDate)
df["date_only"] = pd.to_datetime(df["InvoiceDate"]).dt.date
dim_date = df[["date_only"]].drop_duplicates()
dim_date["year"] = pd.to_datetime(dim_date["date_only"]).dt.year
dim_date["month"] = pd.to_datetime(dim_date["date_only"]).dt.month
dim_date["day"] = pd.to_datetime(dim_date["date_only"]).dt.day
dim_date["weekday"] = pd.to_datetime(dim_date["date_only"]).dt.day_name()
dim_date.columns = ["date_key", "year", "month", "day", "weekday"]
dim_date.to_sql("dim_date", engine, if_exists="append", index=False)
print(f"insert dim_date: {len(dim_date)} แถว")

print("โหลดข้อมูลสำเร็จทั้งหมด (ยังไม่รวม fact_sales)")


# 6. ดึง product_key ที่ Postgres สร้างให้ มาจับคู่กับ stock_code
product_map = pd.read_sql("SELECT product_key, stock_code FROM dim_product", engine)

# 7. เตรียมข้อมูล fact_sales
fact_sales = df[[
    "InvoiceNo", "StockCode", "CustomerID", "date_only",
    "Quantity", "UnitPrice", "total_amount", "is_return"
]].copy()

# 8. join กับ product_map เพื่อแปลง StockCode -> product_key
fact_sales = fact_sales.merge(product_map, left_on="StockCode", right_on="stock_code", how="left")

# 9. เลือกเฉพาะคอลัมน์ที่ตาราง fact_sales ต้องการ เรียงลำดับ + เปลี่ยนชื่อให้ตรง
fact_sales_final = fact_sales[[
    "InvoiceNo", "product_key", "CustomerID", "date_only",
    "Quantity", "UnitPrice", "total_amount", "is_return"
]].copy()
fact_sales_final.columns = [
    "invoice_no", "product_key", "customer_id", "date_key",
    "quantity", "unit_price", "total_amount", "is_return"
]

# 10. insert เข้า fact_sales
fact_sales_final.to_sql("fact_sales", engine, if_exists="append", index=False)
print(f"insert fact_sales: {len(fact_sales_final)} แถว")