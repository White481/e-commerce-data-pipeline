import pandas as pd

# 1. โหลดข้อมูลดิบ
df = pd.read_excel("data/Online Retail.xlsx")
print(f"เริ่มต้น: {df.shape[0]} แถว")

# 2. Drop แถวที่ไม่มี CustomerID
#    เหตุผล: วิเคราะห์ per-customer ไม่ได้ถ้าไม่รู้ว่าใครซื้อ
df = df.dropna(subset=["CustomerID"])
print(f"หลัง drop missing CustomerID: {df.shape[0]} แถว")

# 3. แปลง CustomerID จาก float (17850.0) เป็น int (17850)
#    เหตุผล: ID ควรเป็นเลขจำนวนเต็ม ไม่ใช่ทศนิยม
df["CustomerID"] = df["CustomerID"].astype(int)

# 4. เพิ่มคอลัมน์ is_return
#    เหตุผล: Quantity ติดลบ = การคืนสินค้า ไม่ใช่ error เก็บไว้แยกวิเคราะห์
df["is_return"] = df["Quantity"] < 0

# 5. ลบแถวที่ Description เป็นค่าว่าง (แค่ 1,454 แถว ไม่กระทบมาก)
df = df.dropna(subset=["Description"])
print(f"หลัง drop missing Description: {df.shape[0]} แถว")

# 6. เพิ่มคอลัมน์ total_amount (Quantity x UnitPrice)
#    เหตุผล: ใช้คำนวณ revenue ตอนวิเคราะห์ทีหลัง
df["total_amount"] = df["Quantity"] * df["UnitPrice"]

# 7. เซฟไฟล์ที่ clean แล้ว
df.to_csv("data/cleaned_online_retail.csv", index=False)
print("บันทึกไฟล์ที่ clean แล้วสำเร็จ")
print(df.head())