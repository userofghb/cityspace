import geopandas as gpd
import pandas as pd
import numpy as np
from scipy.spatial import KDTree
import math
import warnings

warnings.filterwarnings("ignore")


def calculate_poi_statistics(
    road_points_path,
    poi_path,
    buffer_distance,
    road_id_col,
    poi_type_col
):
    """
    对每个道路点统计：
    1. POI 总数
    2. POI 类型数量（不同 POI 类型的个数）
    3. 信息熵（POI=0 时熵=0）
    """

    print("读取数据...")
    road_points = gpd.read_file(road_points_path)
    pois = gpd.read_file(poi_path)

    # 坐标系统一
    if road_points.crs != pois.crs:
        pois = pois.to_crs(road_points.crs)

    # 提取坐标
    road_coords = np.array([(g.x, g.y) for g in road_points.geometry])
    poi_coords = np.array([(g.x, g.y) for g in pois.geometry])

    # KDTree 加速空间查询
    poi_tree = KDTree(poi_coords)

    results = []
    total_road_points = len(road_points)

    print("开始统计 POI 信息...")

    for idx, road_row in road_points.iterrows():
        cx, cy = road_coords[idx]

        # 粗筛：查找一定范围内的 POI
        candidate_indices = poi_tree.query_ball_point(
            [cx, cy], buffer_distance * 1.5
        )

        # 精筛：真实距离判断
        valid_poi_indices = []
        for poi_idx in candidate_indices:
            if road_row.geometry.distance(pois.iloc[poi_idx].geometry) <= buffer_distance:
                valid_poi_indices.append(poi_idx)

        # -------- 统计 --------
        if valid_poi_indices:
            buffer_pois = pois.iloc[valid_poi_indices]

            # POI 总数
            total_pois = len(buffer_pois)

            # 各类型数量统计
            poi_counts = buffer_pois[poi_type_col].value_counts()

            # POI 类型数量（不同类型的个数）
            poi_type_count = len(poi_counts)

            # 信息熵（安全计算）
            entropy = 0.0
            for cnt in poi_counts.values:
                p = cnt / total_pois
                if p > 0:
                    entropy -= p * math.log(p)

        else:
            total_pois = 0
            poi_type_count = 0
            entropy = 0.0

        results.append({
            road_id_col: road_row[road_id_col],
            "poic_t": total_pois,
            "poic_c": poi_type_count,
            "en_poic": entropy
        })

        if (idx + 1) % 100 == 0:
            print(f"已处理 {idx + 1}/{total_road_points} 个道路点")

    # 合并回道路点
    result_df = pd.DataFrame(results)
    road_points = road_points.merge(
        result_df,
        on=road_id_col,
        how="left"
    )

    print("统计完成")
    return road_points


def save_results(road_points, output_path):
    """
    保存为 Shapefile + CSV
    """
    # 保存 SHP
    road_points.to_file(output_path, encoding="utf-8")
    print(f"SHP 已保存: {output_path}")
    # 保存 CSV（带坐标）
    csv_path = output_path.replace(".shp", ".csv")
    csv_df = road_points.copy()
    csv_df["x"] = csv_df.geometry.x
    csv_df["y"] = csv_df.geometry.y
    csv_df = csv_df.drop(columns="geometry")
    csv_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"CSV 已保存: {csv_path}")


# ---------------- 主程序 ----------------
if __name__ == "__main__":
    ROAD_POINTS_PATH = "D:/2024srtp/product3/linkn1.shp"
    POI_PATH = "D:/2024srtp/product3/poicut.shp"
    BUFFER_DISTANCE = 50
    ROAD_ID_COL = "TARGET_FID"
    POI_TYPE_COL = "main_tag"
    OUTPUT_PATH = "D:/2024srtp/product3/linkn2.shp"

    result = calculate_poi_statistics(
        road_points_path=ROAD_POINTS_PATH,
        poi_path=POI_PATH,
        buffer_distance=BUFFER_DISTANCE,
        road_id_col=ROAD_ID_COL,
        poi_type_col=POI_TYPE_COL
    )

    save_results(result, OUTPUT_PATH)

