import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os

# =======================
# 1. 参数
# =======================
csv_path = r"D:/2024srtp/finalresult/allcity/主城街道预测结果.csv"
out_shp = r"D:/2024srtp/finalresult/allcity/主城街道预测结果.shp"
keep_label = 1

x_col = "Coord_X"
y_col = "Coord_Y"
label_col = "Pred_Label"

# =======================
# 2. 读取 CSV
# =======================
df = pd.read_csv(csv_path)
print("原始数据量:", len(df))

# =======================
# 3. 按 Pred_Label 筛选
# =======================
df = df[df[label_col] == keep_label].reset_index(drop=True)
print("筛选后数据量:", len(df))

# =======================
# 4. 构造几何
# =======================
geometry = [Point(xy) for xy in zip(df[x_col], df[y_col])]

# ✅ 南京投影：UTM Zone 50N
gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:32650")

# =======================
# 5. 导出 SHP
# =======================
gdf.to_file(out_shp, encoding="utf-8")

print("SHP 已生成:", out_shp)
