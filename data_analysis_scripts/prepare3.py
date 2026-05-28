import geopandas as gpd
from sklearn.neighbors import BallTree
import pandas as pd
import numpy as np

# ======== 参数设置 ========
source_path = "C:/Users/27462/Desktop/2024srtp/result/imageshill.shp"       # 源点数据
target_path = "C:/Users/27462/Desktop/2024srtp/product3/link.shp"       # 目标点数据
output_path = "C:/Users/27462/Desktop/2024srtp/product3/link1.shp"     # 输出结果
search_radius = 20.0                    # 搜索半径，单位与坐标系单位一致
cols_to_average = ["method_exc", "method_e_1", "method_e_2","method_com","method_c_1","method_c_2"]  # 要取平均的字段名

# ======== 1. 读取数据 ========
gdf_source = gpd.read_file(source_path)
gdf_target = gpd.read_file(target_path)

# ======== 2. 坐标系统一 ========
# 如果两者 CRS 不一致，统一到同一个
if gdf_source.crs != gdf_target.crs:
    gdf_target = gdf_target.to_crs(gdf_source.crs)

# ======== 3. 检查单位（重要） ========
# 如果是经纬度坐标（度），需转换到米制坐标（例如 EPSG:3857）
if gdf_source.crs.is_geographic:
    print("检测到坐标为经纬度，将自动转换为 EPSG:32650")
    gdf_source = gdf_source.to_crs("EPSG:32650")
    gdf_target = gdf_target.to_crs("EPSG:32650")

# ======== 4. 建立空间索引（BallTree） ========
coords_source = np.vstack([gdf_source.geometry.x, gdf_source.geometry.y]).T
tree = BallTree(coords_source, metric='euclidean')

# ======== 5. 对每个目标点搜索并计算平均 ========
results = []
for geom in gdf_target.geometry:
    x, y = geom.x, geom.y
    # 在半径 search_radius 内找到所有源点索引
    idx = tree.query_radius([[x, y]], r=search_radius)[0]
    if len(idx) > 0:
        sub = gdf_source.iloc[idx]
        avg_vals = sub[cols_to_average].mean().to_dict()
    else:
        avg_vals = {col: np.nan for col in cols_to_average}
    results.append(avg_vals)

# ======== 6. 将平均结果合并 ========
avg_df = pd.DataFrame(results)
avg_df.columns = [f"{col}_mean" for col in avg_df.columns]
gdf_target = pd.concat([gdf_target.reset_index(drop=True), avg_df], axis=1)

# ======== 7. 输出结果 ========
gdf_target.to_file(output_path)
print(f"处理完成！结果保存为：{output_path}")
