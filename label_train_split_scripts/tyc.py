import geopandas as gpd
import pandas as pd
import os

# =====================================================
# 0. 输出目录
# =====================================================
output_dir = "D:/2024srtp/finalresult/output_points"
os.makedirs(output_dir, exist_ok=True)

# =====================================================
# 1. 读取数据
# =====================================================
print("正在读取数据...")
points_gdf = gpd.read_file("D:/2024srtp/finalresult/newlink1.shp")

area_t = gpd.read_file("D:/2024srtp/product3/t.shp")
area_v = gpd.read_file("D:/2024srtp/product3/y.shp")
area_p = gpd.read_file("D:/2024srtp/product3/c.shp")

area_1 = gpd.read_file("D:/2024srtp/product3/1.shp")
area_2 = gpd.read_file("D:/2024srtp/product3/2.shp")
area_3 = gpd.read_file("D:/2024srtp/product3/3n.shp")

# =====================================================
# 2. 坐标系统一
# =====================================================
print("\n统一坐标系...")
target_crs = points_gdf.crs

for area, name in [
    (area_t, "t"), (area_v, "v"), (area_p, "p"),
    (area_1, "1"), (area_2, "2"), (area_3, "3")
]:
    if area.crs != target_crs:
        area.to_crs(target_crs, inplace=True)
        print(f"{name} 区域已转换坐标系")

print("坐标系统一完成！")

# =====================================================
# 3. 第一阶段裁剪（t / v / p）
# =====================================================
print("\n开始第一阶段裁剪...")
points_t = gpd.clip(points_gdf, area_t)
points_v = gpd.clip(points_gdf, area_v)
points_p = gpd.clip(points_gdf, area_p)

print(f"t: {len(points_t)} | v: {len(points_v)} | p: {len(points_p)}")

# =====================================================
# 4. 第二阶段裁剪函数
# =====================================================
def second_stage_clip(points, prefix, areas):
    result = {}
    for k, poly in areas.items():
        g = gpd.clip(points, poly)
        result[f"{prefix}{k}"] = g
        print(f"  {prefix}{k}: {len(g)}")
    return result

areas_second = {'1': area_1, '2': area_2, '3': area_3}

results_t = second_stage_clip(points_t, 't', areas_second) if len(points_t) else {}
results_v = second_stage_clip(points_v, 'v', areas_second) if len(points_v) else {}
results_p = second_stage_clip(points_p, 'p', areas_second) if len(points_p) else {}

# =====================================================
# 5. 保存结果（Street 列放最后）
# =====================================================
def save_results(results):
    for name, gdf in results.items():
        if gdf.empty:
            print(f"{name} 无数据，跳过")
            continue

        shp_path = os.path.join(output_dir, f"{name}.shp")
        gdf.to_file(shp_path, encoding="utf-8")

        # ===== CSV =====
        df = gdf.drop(columns="geometry").copy()
        df["x"] = gdf.geometry.x
        df["y"] = gdf.geometry.y

        if "Street" in df.columns:
            cols = [c for c in df.columns if c != "Street"]
            cols.append("Street")
            df = df[cols]

        csv_path = os.path.join(output_dir, f"{name}.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

        print(f"已保存 {name}.shp / {name}.csv ({len(gdf)})")

all_results = {}
all_results.update(results_t)
all_results.update(results_v)
all_results.update(results_p)

save_results(all_results)

# =====================================================
# 6. 统计汇总
# =====================================================
summary = []

def stat(name, gdf):
    if gdf.empty:
        return dict(数据集=name, 点数量=0, X范围="无", Y范围="无", X平均="无", Y平均="无")
    return dict(
        数据集=name,
        点数量=len(gdf),
        X范围=f"{gdf.geometry.x.min():.2f}-{gdf.geometry.x.max():.2f}",
        Y范围=f"{gdf.geometry.y.min():.2f}-{gdf.geometry.y.max():.2f}",
        X平均=f"{gdf.geometry.x.mean():.2f}",
        Y平均=f"{gdf.geometry.y.mean():.2f}"
    )

for k, g in all_results.items():
    summary.append(stat(k, g))

summary += [
    stat("stage1_t", points_t),
    stat("stage1_v", points_v),
    stat("stage1_p", points_p),
    stat("原始数据", points_gdf)
]

summary_df = pd.DataFrame(summary)
summary_path = os.path.join(output_dir, "统计汇总.csv")
summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

print("\n全部处理完成 ✔")
print(f"统计文件已保存：{summary_path}")
