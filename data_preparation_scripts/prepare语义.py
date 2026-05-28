import geopandas as gpd
import pandas as pd
import logging

# ---------- 日志 ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 输入文件路径
road_path = "D:/2024srtp/finalresult/allcity/link1.csv"  # 道路点文件（CSV格式）
target_path = "D:/2024srtp/nanjing10m.csv"  # 街景语义分割数据文件
# ---------- 保存 ----------
# 保存为CSV格式（去除几何列，只保存属性数据）
output_path = "D:/2024srtp/finalresult/allcity/link2.csv"
# 缓冲区半径（单位：米）
buffer_radii = [20]  # 可根据需要调整

# 语义分割中的目标列
target_columns = {
    "vegetation": "vegetation",  # 植被
    "building_m": "building",      # 建筑
    "sky_mean": "sky",                # 天空
    "sidewalk_m": "sidewalk"        # 步行道
}

# ---------- 读数据 ----------
logging.info("读取道路点数据...")
# 从CSV读取道路点数据
df_roads = pd.read_csv(road_path)
# 从CSV中提取经纬度并创建几何点
from shapely.geometry import Point
# 检查x和y列的数值范围，判断是否已经是UTM坐标
if 'x' in df_roads.columns and 'y' in df_roads.columns:
    x_min, x_max = df_roads['x'].min(), df_roads['x'].max()
    y_min, y_max = df_roads['y'].min(), df_roads['y'].max()
    
    # 判断是否为经纬度（通常经度范围-180到180，纬度范围-90到90）
    if x_min > -180 and x_max < 180 and y_min > -90 and y_max < 90:
        # 经纬度坐标
        roads = gpd.GeoDataFrame(df_roads, geometry=gpd.points_from_xy(df_roads['x'], df_roads['y']), crs="EPSG:4326")
        roads = roads.to_crs(epsg=32650)  # 转换为米坐标系（UTM）
        logging.info("道路点数据：经纬度坐标，已转换为UTM")
    else:
        # 可能已经是UTM坐标
        roads = gpd.GeoDataFrame(df_roads, geometry=gpd.points_from_xy(df_roads['x'], df_roads['y']), crs="EPSG:32650")
        logging.info("道路点数据：已使用UTM坐标")
else:
    raise KeyError("道路点数据缺少x或y列")

logging.info("读取街景语义分割数据...")
# 从CSV读取数据
df = pd.read_csv(target_path)

# 假设CSV文件中有经纬度列，列名分别为'lon'和'lat'
# 从image列的文件名中提取经纬度
from shapely.geometry import Point

# 检查是否有image列
if 'image' in df.columns:
    # 从文件名中提取经纬度
    def extract_lat_lon(filename):
        try:
            # 文件名格式：id_lon_lat.jpg
            parts = filename.split('_')
            if len(parts) >= 3:
                lon = float(parts[1])
                lat = float(parts[2].split('.jpg')[0])
                return lon, lat
            return None, None
        except:
            return None, None
    
    # 提取经纬度并创建几何点
    df['lon'], df['lat'] = zip(*df['image'].apply(extract_lat_lon))
    
    # 过滤掉无法提取经纬度的行
    valid_rows = (df['lon'].notna()) & (df['lat'].notna())
    df = df[valid_rows].copy()
    
    logging.info(f"从image列提取经纬度，有效行数: {len(df)}")
    
    # 创建几何点
    df['geometry'] = df.apply(lambda row: Point(row['lon'], row['lat']), axis=1)
else:
    raise KeyError("未找到image列，请检查CSV文件结构")

targets = gpd.GeoDataFrame(df, crs="EPSG:4326")  # 假设CSV中的经纬度是WGS84坐标系
targets = targets.to_crs(epsg=32650)  # 转换为米坐标系（UTM）

# 确保所有目标列是数值类型
for col in target_columns.values():
    if col in targets.columns:
        targets[col] = pd.to_numeric(targets[col], errors="coerce").fillna(0)
    else:
        logging.warning(f"Column {col} not found in data, skipping")
        # 从目标列中移除不存在的列
        target_columns = {k: v for k, v in target_columns.items() if v != col}

# 确保几何有效
targets = targets[targets.is_valid].copy()

# 批量处理 ----------
for radius in buffer_radii:
    logging.info(f"开始处理半径 {radius} m ...")

    # 复制 roads，生成 buffer
    buffers = roads[["geometry"]].copy()
    buffers["geometry"] = buffers.geometry.buffer(radius)
    buffers["road_id"] = buffers.index

    # 空间连接（街景点 → buffer）
    joined = gpd.sjoin(buffers, targets, predicate="intersects")

    logging.info(f"半径 {radius} m 匹配到 {len(joined)} 个街景点")

    # 如果没有匹配结果，跳过
    if joined.empty:
        continue

    # 按道路点聚合，计算所有目标列的平均值
    for name, col in target_columns.items():
        if col in joined.columns:
            agg_df = joined.groupby(["road_id"])[col].mean().reset_index()
            # 列名使用要求的格式：vegetation、sky_mean、building_m、sidewalk_m
            agg_df.rename(columns={col: name}, inplace=True)
            # 合并结果到原始 roads
            roads = roads.merge(agg_df, left_index=True, right_on="road_id", how="left").drop(columns="road_id")
            logging.info(f"处理完成 {name} 列")
        else:
            logging.warning(f"Column {col} not found in joined data, skipping {name}")


# 复制数据并移除几何列
roads_csv = roads.copy()
# 提取经纬度（如果需要）
if 'geometry' in roads_csv.columns:
    roads_csv['x'] = roads_csv.geometry.x
    roads_csv['y'] = roads_csv.geometry.y
    roads_csv = roads_csv.drop('geometry', axis=1)
# 保存为CSV
roads_csv.to_csv(output_path, index=False, encoding='utf-8-sig')
logging.info("处理完成，结果已保存为CSV格式")