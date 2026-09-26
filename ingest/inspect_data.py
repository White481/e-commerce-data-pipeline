import pandas as pd

df = pd.read_excel("data/Online Retail.xlsx")

print(df.shape)
print(df.dtypes)
print(df.head())
print(df.isnull().sum())          # เช็คว่ามี missing values ตรงไหนบ้าง
print((df["Quantity"] < 0).sum())  # เช็คจำนวน returns (quantity ติดลบ)