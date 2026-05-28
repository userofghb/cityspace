import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ===== 1. 读取 CSV =====
csv_path = "D:/2024srtp/1225 主城微博/1225 weibo.csv"
df = pd.read_csv(csv_path)

# 字段名（按你的实际 CSV 修改）
place_col = "地点名"
lon_col = "经度"
lat_col = "纬度"

# ===== 2. 按“地点名”去重 =====
# 默认保留第一次出现的记录
df_unique = df.drop_duplicates(subset=[place_col], keep="first")

# ===== 3. 保存为 CSV =====
out_path = "D:/2024srtp/1225 主城微博/unique_by_place.csv"
df_unique.to_csv(out_path, index=False, encoding="utf-8-sig")

print("按地点名去重完成，输出：", out_path)

