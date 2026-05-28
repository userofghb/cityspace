import geopandas as gpd

# ========== 路径 ==========
points_path = "D:/2024srtp/finalresult/linkn.shp"
area_a_path = "D:/2024srtp/1107shp文件更新(1)/1107shp文件更新/测试边界1107.shp"
area_b_path = "D:/2024srtp/finalresult/20260305数据更新/街道验证集260305.shp"
output_path = "D:/2024srtp/finalresult/newlink1.shp"

# ========== 读取 ==========
points = gpd.read_file(points_path)
area_a = gpd.read_file(area_a_path)
area_b = gpd.read_file(area_b_path)

# ========== CRS 统一 ==========
# 以 points 的 CRS 为准（也可以改为任意一致的 CRS）
if points.crs is None:
    raise ValueError("points 图层没有 CRS，请先设置。")
if area_a.crs != points.crs:
    area_a = area_a.to_crs(points.crs)
if area_b.crs != points.crs:
    area_b = area_b.to_crs(points.crs)

# ========== 确保有 Street 字段（备份原值） ==========
if "Street" not in points.columns:
    # 如果没有原字段，则创建空字符串（或根据需要）
    points["Street"] = None

# ========== 计算布尔掩码（速度较快的做法：使用 unary_union） ==========
# 把面合并为单个几何以便批量判断（适用于多面、MultiPolygon）
union_a = area_a.unary_union
union_b = area_b.unary_union

# mask_a: 在 A 内的点（Boolean Series）
mask_a = points.geometry.within(union_a)

# mask_b_sub: 在 B 内但只计算 A 内子集（Boolean Series，索引与 points 对齐）
mask_b_sub = points.loc[mask_a, "geometry"].within(union_b)

# ========== 更新 Street 字段（仅对 A 内点） ==========
# 将 A 内点的 Street 设置为 1（在 B）或 0（不在 B）
# mask_b_sub 的索引正好是 points 中的那些行，因此可以直接赋值
points.loc[mask_a, "Street"] = mask_b_sub.astype(int)

# ========== （可选）把 Street 强制为整型并清理临时列 ==========
# 如果你希望最终Street为整数类型
points["Street"] = points["Street"].astype("Int64")  # 支持缺失值的整型

# ========== 保存 ==========
points.to_file(output_path)
print("完成。已保存到：", output_path)
print(f"统计：在 A 的点数 = {mask_a.sum()}, 在 A 且在 B 的点数 = {mask_b_sub.sum()}")