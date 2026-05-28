import geopandas as gpd
import pandas as pd
import logging

# ---------- 日志 ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

road_path = "D:/2024srtp/finalresult/allcity/prepare.gpkg"
target_path = "D:/2024srtp/nanjing10m2_yolo_4090/images.shp"

buffer_radii = [25]  # 单位：米
type_field = "type"
value_field = "num"

# ---------- 读数据 ----------
roads = gpd.read_file(road_path).to_crs(epsg=32650)  # 转换为米坐标系（UTM）
targets = gpd.read_file(target_path).to_crs(epsg=32650)

# 确保 num 列是整数
targets[value_field] = pd.to_numeric(targets[value_field], errors="coerce").fillna(0).astype(int)

# 确保几何有效（不改成 buffer(0)，保持点）
targets = targets[targets.is_valid].copy()

# 定义需要计算的类型
required_types = ['car', 'boat', 'person', 'bus', 'truck', 'umbrella', 'traffic', 'motorcycle', 'bicycle']

# 只保留需要的类型
filtered_targets = targets[targets[type_field].isin(required_types)].copy()

# 提取需要的类别
all_types = filtered_targets[type_field].dropna().unique()

# ---------- 批量处理 ----------
for radius in buffer_radii:
    logging.info(f"开始处理半径 {radius} m ...")

    # 复制 roads，生成 buffer
    buffers = roads[["geometry"]].copy()
    buffers["geometry"] = buffers.geometry.buffer(radius)
    buffers["road_id"] = buffers.index

    # 空间连接（目标点 → buffer）
    joined = gpd.sjoin(buffers, filtered_targets, predicate="intersects")

    logging.info(f"半径 {radius} m 匹配到 {len(joined)} 个点")

    # 如果没有匹配结果，跳过
    if joined.empty:
        continue

    # 按道路点和 type 聚合
    agg_df = joined.groupby(["road_id", type_field])[value_field].sum().reset_index()

    # 生成透视表（行=road_id，列=type，值=统计和）
    pivot_df = agg_df.pivot(index="road_id", columns=type_field, values=value_field).reindex(columns=all_types, fill_value=0)

    # 列名改成 sum_xxx_radius
    pivot_df.columns = [f"sum_{t}_{radius}" for t in pivot_df.columns]
    pivot_df = pivot_df.reset_index()

    # 合并结果到原始 roads
    roads = roads.merge(pivot_df, left_index=True, right_on="road_id", how="left").drop(columns="road_id")

# ---------- 保存 ----------
# 保存为CSV格式（去除几何列，只保存属性数据）
output_path = "D:/2024srtp/finalresult/allcity/link1.csv"
# 复制数据并移除几何列
roads_csv = roads.copy()
# 提取经纬度（如果需要）
if 'geometry' in roads_csv.columns:
    roads_csv['lon'] = roads_csv.geometry.x
    roads_csv['lat'] = roads_csv.geometry.y
    roads_csv = roads_csv.drop('geometry', axis=1)
# 保存为CSV
roads_csv.to_csv(output_path, index=False, encoding='utf-8-sig')
logging.info("处理完成，结果已保存为CSV格式")