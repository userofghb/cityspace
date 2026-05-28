import geopandas as gpd
import pandas as pd
import os
import time

# ================= 用户参数 =================
points_csv = r"D:/2024srtp/finalresult/allcity/link2.csv"  # CSV格式输入
segments_shp = r"D:\2024srtp\v1.0\project\getstreet\edge_outputs1\edge_speed_final.shp"
out_gpkg = r"D:\2024srtp\finalresult\allcity\link.gpkg"  # GPKG格式输出

search_radius_m = 25.0   # 如果想强制匹配最近一条，改成 None
speed_field = "avg_speed_"   #请确认字段名
# ===========================================

start_time = time.time()
print("========== 开始执行 ==========")

# ========= 1. 读取数据 =========
print("读取数据...")
# 从CSV读取点数据
import pandas as pd
from shapely.geometry import Point

df_pts = pd.read_csv(points_csv)
# 从CSV中提取x，y列并创建几何点
pts = gpd.GeoDataFrame(
    df_pts,
    geometry=[Point(x, y) for x, y in zip(df_pts['x'], df_pts['y'])],
    crs="EPSG:32650"  # 假设输入的x，y是UTM坐标
)

segs = gpd.read_file(segments_shp)

print("原始点数量:", len(pts))
print("路段数量:", len(segs))
print("路段字段:", list(segs.columns))

# ========= 2. CRS 统一 =========
if pts.crs is None or segs.crs is None:
    raise ValueError("两个 shp 必须有 CRS")

if pts.crs.is_geographic:
    print("检测到地理坐标系，自动投影到 UTM...")
    utm_crs = pts.estimate_utm_crs()
    pts = pts.to_crs(utm_crs)
    segs = segs.to_crs(utm_crs)
else:
    if pts.crs != segs.crs:
        segs = segs.to_crs(pts.crs)

# ========= 3. 字段检查 =========
if speed_field not in segs.columns:
    raise ValueError(f"找不到字段 {speed_field}")

# ========= 4. 最近邻匹配 =========
print("开始最近邻匹配...")

joined = gpd.sjoin_nearest(
    pts,
    segs[[speed_field, 'geometry']],
    how="left",
    distance_col="dist_to_seg",
    max_distance=search_radius_m
)

print("匹配后记录数:", len(joined))

# ========= 5. 强制一对一（稳定修复版本） =========
print("强制每个点只保留最近一条...")

joined["_orig_index"] = joined.index

joined = (
    joined
    .sort_values("dist_to_seg")
    .drop_duplicates(subset="_orig_index", keep="first")
    .drop(columns="_orig_index")
)
# ========= 6. 清理字段 =========
joined = joined.rename(columns={speed_field: "avg_speed"})

if "index_right" in joined.columns:
    joined = joined.drop(columns=["index_right"])

# ========= 7. 匹配统计 =========
missing = joined["avg_speed"].isna().sum()
print("未匹配点数量:", missing)

# ========= 8. 保存结果 =========
print("保存结果...")
# 保留所有原始属性，并确保是GeoDataFrame
result = gpd.GeoDataFrame(
    joined.drop(['dist_to_seg'], axis=1, errors='ignore'),  # 移除距离列，保留其他所有属性
    geometry=joined['geometry'],
    crs=joined.crs
)
result.to_file(out_gpkg, driver="GPKG")

print("输出文件:", out_gpkg)
print("结果保留原始点的所有属性，并添加了平均车速列")
print("总耗时: %.2f 秒" % (time.time() - start_time))
print("========== 完成 ==========")