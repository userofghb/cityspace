import geopandas as gpd
from shapely.geometry import Point, MultiPoint, LineString, MultiLineString
from shapely.ops import split, unary_union
from shapely.strtree import STRtree
import warnings
import logging
import time
warnings.filterwarnings("ignore", category=UserWarning)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cj1_optimization.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------- 参数设置 ----------
input_roads  = "D:/2024srtp/road/newroad/zcqroad3.shp"
input_points = "D:/2024srtp/finalresult/allcity/主城街道预测结果.shp"
output_lines = "D:/2024srtp/finalresult/allcity/roads_splitt.shp"
output_polygons = "D:/2024srtp/finalresult/allcity/road_clusterst.shp"
hot_segments_output = "D:/2024srtp/finalresult/allcity/hot_segmentst.shp"
epsg_proj = 32650

buffer_width = 15        # 缓冲带宽度（米）
match_buffer = 10        # 点匹配缓冲（米）
density_threshold = 50      # 点密度阈值（点/千米）

# ---------- Step 1：读取数据 ----------
logger.info("开始读取数据...")
start_time = time.time()
roads = gpd.read_file(input_roads).to_crs(epsg=epsg_proj)
points = gpd.read_file(input_points).to_crs(epsg=epsg_proj)
roads = roads.explode(index_parts=False)
end_time = time.time()
logger.info(f"道路数据加载完成，共 {len(roads)} 条道路")
logger.info(f"热点点数据加载完成，共 {len(points)} 个点")
logger.info(f"数据加载耗时: {end_time - start_time:.2f}秒")
logger.info("道路与热点点数据加载完成")

# ---------- Step 2：提取交点和端点 ----------
logger.info("开始提取交点和端点...")
start_time = time.time()

# 首先添加所有道路的端点
intersection_points = []
for line in roads.geometry:
    if isinstance(line, LineString):
        intersection_points.extend([Point(line.coords[0]), Point(line.coords[-1])])
    elif isinstance(line, MultiLineString):
        for part in line.geoms:
            intersection_points.extend([Point(part.coords[0]), Point(part.coords[-1])])

# 优化：使用空间索引快速筛选可能相交的道路对
logger.info("构建道路空间索引...")
sindex = roads.sindex

# 只计算可能相交的道路对
processed_pairs = set()
road_geoms = list(roads.geometry)
road_bounds = [geom.bounds for geom in road_geoms]

for i, road in enumerate(road_geoms):
    # 找到可能与当前道路相交的其他道路
    possible_matches_index = list(sindex.intersection(road.bounds))
    
    for j in possible_matches_index:
        if i >= j:  # 避免重复计算
            continue
        
        pair_key = (i, j)
        if pair_key in processed_pairs:
            continue
        processed_pairs.add(pair_key)
        
        other_road = road_geoms[j]
        # 快速边界检查
        r1_minx, r1_miny, r1_maxx, r1_maxy = road_bounds[i]
        r2_minx, r2_miny, r2_maxx, r2_maxy = road_bounds[j]
        
        # 如果边界不相交，跳过
        if r1_maxx < r2_minx or r1_minx > r2_maxx or r1_maxy < r2_miny or r1_miny > r2_maxy:
            continue
        
        inter = road.intersection(other_road)
        
        if inter.is_empty:
            continue
        if inter.geom_type == 'Point':
            intersection_points.append(inter)
        elif inter.geom_type == 'MultiPoint':
            intersection_points.extend(inter.geoms)
    
    # 显示进度
    if (i + 1) % 1000 == 0 or (i + 1) == len(road_geoms):
        logger.info(f"交点计算进度: {i + 1}/{len(road_geoms)}")

cut_points = MultiPoint(intersection_points)
end_time = time.time()
logger.info(f"提取完成，共 {len(intersection_points)} 个切割点，耗时: {end_time - start_time:.2f}秒")

# ---------- Step 3：拆分 ----------
logger.info("开始道路切割...")
start_time = time.time()

# 为切割点建立空间索引
cut_points_tree = STRtree(cut_points.geoms)

def split_line_preserve_shape(line, points_tree):
    try:
        # 确保line是几何对象
        if not hasattr(line, 'buffer'):
            return [line]
        
        # 使用空间索引快速筛选可能在道路附近的切割点
        possible_cut_points = points_tree.query(line.buffer(0.1))  # 0.1米缓冲
        
        # 过滤出有效的几何对象
        valid_points = []
        for pt in possible_cut_points:
            if hasattr(pt, 'buffer'):
                valid_points.append(pt)
        
        splitters = [pt.buffer(0.01) for pt in valid_points if line.distance(pt) < 1e-6]
        if not splitters:
            return [line]
        cutter = unary_union(splitters)
        try:
            parts = split(line, cutter)
            return list(parts.geoms)
        except Exception:
            return [line]
    except Exception as e:
        logger.error(f"split_line_preserve_shape 出错: {e}")
        return [line]

def process_road(geom, points_tree):
    try:
        # 确保geom是几何对象
        if not hasattr(geom, 'is_empty'):
            return []
        
        if geom.is_empty:
            return []
        if isinstance(geom, LineString):
            return split_line_preserve_shape(geom, points_tree)
        elif isinstance(geom, MultiLineString):
            result = []
            for part in geom.geoms:
                result.extend(split_line_preserve_shape(part, points_tree))
            return result
        return []
    except Exception as e:
        logger.error(f"process_road 出错: {e}")
        return []

# 串行处理道路切割
split_lines = []

for i, geom in enumerate(roads.geometry):
    try:
        split_lines.extend(process_road(geom, cut_points_tree))
    except Exception as e:
        logger.error(f"处理道路 {i} 时出错: {e}")
    
    # 显示进度
    if (i + 1) % 100 == 0 or (i + 1) == len(roads):
        logger.info(f"道路切割进度: {i + 1}/{len(roads)}")

split_edges = gpd.GeoDataFrame(geometry=split_lines, crs=roads.crs)
split_edges.reset_index(drop=True, inplace=True)
split_edges.to_file(output_lines)
end_time = time.time()
logger.info(f"道路切割完成，共 {len(split_edges)} 条，耗时: {end_time - start_time:.2f}秒")

# ---------- Step 4：计算点密度 ----------
logger.info("开始计算点密度...")
start_time = time.time()
split_edges["num_points"] = 0
split_edges["length_m"] = split_edges.length
split_edges["density"] = 0  # 点密度（点/千米）

points_sindex = points.sindex

# 计算点密度
def process_segment(segment_idx, segment_geom, segment_length, points_gdf, points_index, buffer_dist):
    buf = segment_geom.buffer(buffer_dist)
    # 空间索引初筛
    cand_idx = list(points_index.intersection(buf.bounds))
    if len(cand_idx) == 0:
        n = 0
    else:
        cand_points = points_gdf.iloc[cand_idx]
        matched = cand_points[cand_points.intersects(buf)]
        n = len(matched)
    # 计算点密度（点/千米）
    length_km = segment_length / 1000
    density = n / length_km if length_km > 0 else 0
    return segment_idx, n, density

# 准备任务
tasks = []
for idx, row in split_edges.iterrows():
    tasks.append((idx, row.geometry, row["length_m"], points, points_sindex, match_buffer))

# 串行处理
results = {}

for i, task in enumerate(tasks):
    idx, segment_geom, segment_length, points_gdf, points_index, buffer_dist = task
    try:
        segment_idx, n, density = process_segment(idx, segment_geom, segment_length, points_gdf, points_index, buffer_dist)
        results[segment_idx] = (n, density)
    except Exception as exc:
        logger.error(f"处理线段 {idx} 时出错: {exc}")
    
    # 打印进度
    if (i + 1) % 1000 == 0 or (i + 1) == len(tasks):
        logger.info(f"计算点密度进度: {i + 1}/{len(tasks)}")

# 更新结果
for idx, (n, density) in results.items():
    split_edges.at[idx, "num_points"] = n
    split_edges.at[idx, "density"] = density

end_time = time.time()
logger.info(f"点密度计算完成，耗时: {end_time - start_time:.2f}秒")

# ---------- Step 5：按点密度筛选 ----------
logger.info("开始筛选热点线段...")
start_time = time.time()
hot_segments = split_edges[split_edges["density"] >= density_threshold]
hot_segments.to_file(hot_segments_output)
end_time = time.time()
logger.info(f"热点线段输出完成，共 {len(hot_segments)} 条，耗时: {end_time - start_time:.2f}秒")

# ---------- Step 6：生成热点缓冲区 ----------
logger.info("开始生成热点面域...")
start_time = time.time()
if len(hot_segments) > 0:
    hot_buffers = hot_segments.geometry.buffer(buffer_width)
    buffer_union = unary_union(hot_buffers)

    if buffer_union.geom_type == 'Polygon':
        polygons = [buffer_union]
    elif buffer_union.geom_type == 'MultiPolygon':
        polygons = list(buffer_union.geoms)
    else:
        polygons = []

    gdf_polygons = gpd.GeoDataFrame(geometry=polygons, crs=roads.crs)
else:
    # 没有热点线段，生成空的 GeoDataFrame
    gdf_polygons = gpd.GeoDataFrame(geometry=[], crs=roads.crs)

gdf_polygons.to_file(output_polygons)
end_time = time.time()
logger.info(f"热点面域生成完成，共 {len(gdf_polygons)} 个，耗时: {end_time - start_time:.2f}秒")