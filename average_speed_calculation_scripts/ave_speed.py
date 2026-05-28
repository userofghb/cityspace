#!/usr/bin/env python3
# ave_speed_optimized_with_peak_filter.py
# 完整优化版：数据清洗、KDTree 批量吸附、并行分块、候选路径限速
# 新增：按时间列去除早晚高峰（可自定义时间列与高峰时间段）

print("=== FILE LOADED ===")

import os
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import ast
import math
from datetime import time as dtime

import pandas as pd
import numpy as np
import networkx as nx
import geopandas as gpd
import osmnx as ox
from shapely.geometry import LineString, MultiLineString

# KDTree (scipy 优先)
try:
    from scipy.spatial import cKDTree as KDTree
except Exception:
    KDTree = None

# ============================
# 默认配置（可在文件顶部修改或通过命令行参数覆盖）
# ============================
CSV_PATH = r"D:/BaiduNetdiskDownload/0111.xlsx"
ROAD_SHP = r"D:/2024srtp/road/newroad/zcqroad.shp"
OUTPUT_DIR = "edge_outputs1"

CHUNKSIZE = 5000
NUM_WORKERS = 2

TOL_REL = 0.15
MAX_CANDIDATES_SCAN = 1

MIN_DURATION_S = 30
MAX_SPEED_KMH = 200
MIN_SPEED_KMH = 1

COL_DEP_LON = "DEP_LON"
COL_DEP_LAT = "DEP_LAT"
COL_DEST_LON = "DEST_LON"
COL_DEST_LAT = "DEST_LAT"
COL_DRIVE_MILE = "DRIVE_MILE"
COL_DRIVE_TIME = "DRIVE_TIME"

PROGRESS_INTERVAL = 500  # 每处理多少行打印一次进度

# 全局（每个 worker 会初始化一份）
G = None
_NODE_LIST = None       # list of node keys (tuples)
_NODE_COORDS = None     # numpy array shape (n_nodes, 2) of [lon, lat]
_KDTREE = None          # KDTree object (or None)
_INDEX_TO_NODE = None   # dict index -> node key

# ============================
def coord_key(lon, lat, p=6):
    return (round(float(lon), p), round(float(lat), p))

# ============================
def build_graph_from_road_shp(road_fp):
    """从 road.shp 建图：节点为坐标点 (lon, lat)，边权 length（米）"""
    print(">>> Building topology graph ...")
    roads = gpd.read_file(road_fp)
    print("Road CRS:", roads.crs)

    roads_wgs = roads.to_crs(epsg=4326)
    # 用投影计算米长（根据你的 shp 选择适合的投影，原来用 32650）
    roads_m = roads.to_crs(epsg=32650)

    G_local = nx.Graph()

    for geom_wgs, geom_m in zip(roads_wgs.geometry, roads_m.geometry):
        if geom_wgs is None:
            continue

        if isinstance(geom_wgs, MultiLineString):
            lines = geom_wgs.geoms
            lines_m = geom_m.geoms
        else:
            lines = [geom_wgs]
            lines_m = [geom_m]

        for lw, lm in zip(lines, lines_m):
            coords = list(lw.coords)
            coords_m = list(lm.coords)

            for i in range(len(coords) - 1):
                u = coord_key(coords[i][0], coords[i][1])
                v = coord_key(coords[i+1][0], coords[i+1][1])

                if u == v:
                    continue

                length = LineString([coords_m[i], coords_m[i+1]]).length

                if not G_local.has_node(u):
                    G_local.add_node(u, x=u[0], y=u[1])
                if not G_local.has_node(v):
                    G_local.add_node(v, x=v[0], y=v[1])

                # 若边重复，保留最短长度
                if G_local.has_edge(u, v):
                    if G_local[u][v].get("length", 1e30) > length:
                        G_local[u][v]["length"] = length
                else:
                    G_local.add_edge(u, v, length=length)

    print(">>> Graph built:", len(G_local.nodes), "nodes,", len(G_local.edges), "edges")
    return G_local

# ============================
def _build_spatial_index(G_local):
    """构建节点坐标数组与 KDTree（如果可用）"""
    node_list = []
    coords = []
    for node, data in G_local.nodes(data=True):
        node_list.append(node)
        coords.append((data["x"], data["y"]))
    node_coords = np.array(coords, dtype=float) if coords else np.zeros((0,2), dtype=float)
    if KDTree is not None and node_coords.shape[0] > 0:
        kdt = KDTree(node_coords)
    else:
        kdt = None
    index_to_node = {i: n for i, n in enumerate(node_list)}
    return node_list, node_coords, kdt, index_to_node

# ============================
def load_graph_worker(road_fp):
    """每个 worker 初始化时运行一次，加载图并建立 KDTree 索引"""
    global G, _NODE_LIST, _NODE_COORDS, _KDTREE, _INDEX_TO_NODE
    print("[worker] loading road graph ...")
    G = build_graph_from_road_shp(road_fp)
    _NODE_LIST, _NODE_COORDS, _KDTREE, _INDEX_TO_NODE = _build_spatial_index(G)
    print("[worker] spatial index built. nodes:", len(_NODE_LIST), "KDTree:", _KDTREE is not None)

# ============================
def snap_points_batch(lon_arr, lat_arr):
    """
    批量吸附点到最近节点，返回 node list（长度与输入相同），无法匹配处返回 None。
    lon_arr, lat_arr: 1D array-like (floats)
    """
    global _NODE_COORDS, _NODE_LIST, _KDTREE, _INDEX_TO_NODE
    n_points = len(lon_arr)
    res = [None] * n_points
    if _NODE_COORDS is None or _NODE_COORDS.shape[0] == 0:
        return res

    pts = np.column_stack([np.array(lon_arr, dtype=float), np.array(lat_arr, dtype=float)])

    if _KDTREE is not None:
        dists, idxs = _KDTREE.query(pts)
        # 向量化处理，提高性能
        res = [_INDEX_TO_NODE.get(int(idx), None) for idx in idxs]
    else:
        # fallback: vectorized squared distance (may be memory-heavy if many points * many nodes)
        # compute in blocks if necessary
        n_nodes = _NODE_COORDS.shape[0]
        # if n_points * n_nodes too large, compute in chunks of points
        max_cells = 50_000_000  # heuristic: 如果大于这个就分块
        if n_points * n_nodes > max_cells:
            # chunk points to reduce memory
            chunk_size = max(1, int(max_cells // n_nodes))
            start = 0
            while start < n_points:
                end = min(n_points, start + chunk_size)
                subpts = pts[start:end]  # shape (m,2)
                diffs = _NODE_COORDS[None, :, :] - subpts[:, None, :]
                d2 = np.einsum("ijk,ijk->ij", diffs, diffs)
                idxs = np.argmin(d2, axis=1)
                for i_local, idx in enumerate(idxs):
                    res[start + i_local] = _INDEX_TO_NODE.get(int(idx), None)
                start = end
        else:
            diffs = _NODE_COORDS[None, :, :] - pts[:, None, :]
            d2 = np.einsum("ijk,ijk->ij", diffs, diffs)
            idxs = np.argmin(d2, axis=1)
            res = [_INDEX_TO_NODE.get(int(idx), None) for idx in idxs]

    return res

# ============================
def route_length_m(route):
    return sum(G[a][b]["length"] for a, b in zip(route[:-1], route[1:]))

# ============================
def best_path(u, v, drive_m_km):
    """返回 (route, length_m) 或 (None, None)"""
    if u is None or v is None:
        return None, None
    try:
        # 使用Dijkstra算法，通常比默认算法更快
        shortest = nx.shortest_path(G, u, v, weight="length", method="dijkstra")
    except Exception:
        return None, None

    best = shortest
    best_len = route_length_m(shortest)

    if pd.isna(drive_m_km):
        return best, best_len

    target = drive_m_km * 1000.0
    best_err = abs(best_len - target) / max(target, 1.0)

    # 仅在最短路径误差明显时才枚举多路径，避免大量计算
    # 减少多路径搜索的数量以提高性能
    if best_err > 0.3 and MAX_CANDIDATES_SCAN > 0:
        gen = nx.shortest_simple_paths(G, u, v, weight="length")
        for i, r in enumerate(gen):
            if i >= min(MAX_CANDIDATES_SCAN, 2):  # 限制搜索路径数量
                break
            l = route_length_m(r)
            err = abs(l - target) / max(target, 1.0)
            if err < best_err:
                best, best_len, best_err = r, l, err
            if err < TOL_REL:
                break

    return best, best_len

# ============================
# 时间过滤（早晚高峰）相关工具
def parse_peak_windows(s):
    """解析字符串形式的高峰时间段，例如 "07:00-09:00,17:00-19:00" -> [(time(7,0), time(9,0)), ...]"""
    res = []
    if not s:
        return res
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' not in part:
            continue
        a, b = part.split('-', 1)
        try:
            if ':' in a:
                ah, am = [int(x) for x in a.split(':')]
            else:
                ah, am = int(a), 0
            if ':' in b:
                bh, bm = [int(x) for x in b.split(':')]
            else:
                bh, bm = int(b), 0
            res.append((dtime(ah, am), dtime(bh, bm)))
        except Exception:
            continue
    return res


def _time_in_window(tobj, start, end):
    # 支持跨午夜区间
    if start <= end:
        return (tobj >= start) and (tobj < end)
    else:
        # e.g. 23:00-02:00
        return (tobj >= start) or (tobj < end)


def is_timestamp_in_peaks(ts, windows):
    if ts is pd.NaT or windows is None or len(windows) == 0:
        return False
    t = ts.time()
    for s, e in windows:
        if _time_in_window(t, s, e):
            return True
    return False


def filter_peak_hours_df(df, time_col, windows):
    """按时间列过滤掉位于 windows 中的记录（去除高峰）。如果 time_col 不存在则不做任何过滤。"""
    if not time_col or time_col not in df.columns:
        print(f">>> time column '{time_col}' not found, skipping peak-hour filtering")
        return df
    df = df.copy()
    # 尝试解析为 datetime（若已经是 datetime 则保持不变）
    # 支持形如 20230111135726 的时间格式
    df[time_col] = pd.to_datetime(df[time_col].astype(str), format='%Y%m%d%H%M%S', errors='coerce')
    before = len(df)
    # 若时间列解析失败的行，保守地先删除
    if df[time_col].isna().any():
        df = df[~df[time_col].isna()]
    if windows:
        mask = df[time_col].apply(lambda ts: is_timestamp_in_peaks(ts, windows))
        df = df[~mask]
    print(f">>> peak filter ({time_col}): {before} -> {len(df)}")
    return df

# ============================
def clean_xlsx_dataframe(df, time_col=None, peak_windows=None):
    """对原始 DataFrame 做清洗、去重、异常过滤，返回清洗后 DataFrame
       新增：可按时间列去除高峰时段
    """
    print(">>> cleaning raw data ...")
    df = df.copy()
    df.columns = df.columns.str.strip()

    # 保留关键列（若不存在会 KeyError）
    need_cols = [
        COL_DEP_LON, COL_DEP_LAT,
        COL_DEST_LON, COL_DEST_LAT,
        COL_DRIVE_MILE, COL_DRIVE_TIME
    ]
    for c in need_cols:
        if c not in df.columns:
            raise KeyError(f"Missing required column: {c}")

    df = df[need_cols + ([time_col] if (time_col and time_col in df.columns) else [])]

    # 转数值
    for c in need_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 检测并修正经纬度被放大的情况（如 118778547 -> 118.778547）
    lon_max = df[COL_DEP_LON].abs().max(skipna=True)
    if lon_max is not None and lon_max > 180:
        print(">>> detected large lon values (likely scaled). Dividing lon/lat by 1e6.")
        for c in [COL_DEP_LON, COL_DEP_LAT, COL_DEST_LON, COL_DEST_LAT]:
            df[c] = df[c] / 1e6

    before = len(df)
    df = df.dropna(subset=need_cols)
    print(f">>> dropna: {before} -> {len(df)}")

    # 按时间列去除高峰（可选）
    if time_col and time_col in df.columns and peak_windows:
        df = filter_peak_hours_df(df, time_col, peak_windows)

    # 经纬度合理范围过滤（中国范围大致）
    before = len(df)
    df = df[
        df[COL_DEP_LON].between(70, 140) &
        df[COL_DEST_LON].between(70, 140) &
        df[COL_DEP_LAT].between(10, 55) &
        df[COL_DEST_LAT].between(10, 55)
    ]
    print(f">>> geo filter: {before} -> {len(df)}")

    # 行程时间（分钟）与行程里程（km）过滤
    before = len(df)
    df = df[(df[COL_DRIVE_TIME] > 0) & (df[COL_DRIVE_TIME] <= 24 * 60)]
    print(f">>> time filter: {before} -> {len(df)}")
    before = len(df)
    df = df[(df[COL_DRIVE_MILE] > 0) & (df[COL_DRIVE_MILE] < 500)]
    print(f">>> mile filter: {before} -> {len(df)}")

    # 去除起终点相同的记录
    before = len(df)
    df = df[~((df[COL_DEP_LON] == df[COL_DEST_LON]) & (df[COL_DEP_LAT] == df[COL_DEST_LAT]))]
    print(f">>> same-point filter: {before} -> {len(df)}")

    # 去重
    before = len(df)
    df = df.drop_duplicates(subset=[COL_DEP_LON, COL_DEP_LAT, COL_DEST_LON, COL_DEST_LAT, COL_DRIVE_MILE, COL_DRIVE_TIME])
    print(f">>> dedup: {before} -> {len(df)}")

    df = df.reset_index(drop=True)
    print(">>> cleaning done, final rows:", len(df))
    return df

# ============================
def process_chunk(df, chunk_id, params):
    """处理单个 chunk：批量吸附 -> 每行做路径并分配时间 -> 输出中间 csv"""
    # 检查是否已经处理过
    output_file = os.path.join(params["output_dir"], f"edge_chunk_{chunk_id:06d}.csv")
    if os.path.exists(output_file):
        print(f">>> chunk {chunk_id} already processed, skipping")
        return output_file
    
    t0 = time.time()
    print(f">>> processing chunk {chunk_id}, rows={len(df)}")

    # 强制数值类型并过滤缺失
    df[COL_DEP_LON] = pd.to_numeric(df[COL_DEP_LON], errors="coerce")
    df[COL_DEP_LAT] = pd.to_numeric(df[COL_DEP_LAT], errors="coerce")
    df[COL_DEST_LON] = pd.to_numeric(df[COL_DEST_LON], errors="coerce")
    df[COL_DEST_LAT] = pd.to_numeric(df[COL_DEST_LAT], errors="coerce")
    df[COL_DRIVE_MILE] = pd.to_numeric(df[COL_DRIVE_MILE], errors="coerce")
    df[COL_DRIVE_TIME] = pd.to_numeric(df[COL_DRIVE_TIME], errors="coerce")

    df = df.dropna(subset=[COL_DEP_LON, COL_DEP_LAT, COL_DEST_LON, COL_DEST_LAT, COL_DRIVE_MILE, COL_DRIVE_TIME])
    if df.empty:
        print(f">>> chunk {chunk_id} empty after dropna")
        return None

    # 批量吸附（起点/终点）
    dep_lons = df[COL_DEP_LON].values
    dep_lats = df[COL_DEP_LAT].values
    dst_lons = df[COL_DEST_LON].values
    dst_lats = df[COL_DEST_LAT].values

    u_nodes = snap_points_batch(dep_lons, dep_lats)
    v_nodes = snap_points_batch(dst_lons, dst_lats)

    rows = df.reset_index(drop=True)
    out = []
    N = len(rows)
    for i in range(N):
        if i % PROGRESS_INTERVAL == 0 and i > 0:
            print(f"[chunk {chunk_id}] processed {i}/{N}, elapsed {round(time.time()-t0,1)}s")
        u = u_nodes[i]
        v = v_nodes[i]
        if u is None or v is None:
            continue
        # dur in seconds (驱动时间列单位假设为分钟)
        try:
            dur_s = float(rows.at[i, COL_DRIVE_TIME]) * 60.0
        except Exception:
            continue
        if dur_s <= params["min_duration_s"]:
            continue
        drive_m_km = rows.at[i, COL_DRIVE_MILE]
        route, route_len = best_path(u, v, drive_m_km)
        if route is None:
            continue
        seg_lens = [G[a][b]["length"] for a, b in zip(route[:-1], route[1:])]
        total_len = sum(seg_lens)
        if total_len <= 0:
            continue
        for (a, b), seg_len in zip(zip(route[:-1], route[1:]), seg_lens):
            share = seg_len / total_len
            out.append((a, b, seg_len, dur_s * share))

    if not out:
        print(f">>> chunk {chunk_id} no output (elapsed {round(time.time()-t0,1)}s)")
        return None

    tmp = pd.DataFrame(out, columns=["u", "v", "dist_m", "time_s"])
    agg = tmp.groupby(["u", "v"]).agg(
        tot_dist_m=("dist_m", "sum"),
        tot_time_s=("time_s", "sum"),
        cnt=("time_s", "count")
    ).reset_index()

    agg.to_csv(output_file, index=False)

    print(f">>> chunk {chunk_id} saved: {output_file}  time: {round(time.time()-t0,1)}s")
    return output_file

# ============================
def main(args):
    print("=== ENTER MAIN ===")
    os.makedirs(args.output_dir, exist_ok=True)

    print("INPUT:", args.csv)
    print("ROAD:", args.road_shp)
    print("chunksize:", args.chunksize, "workers:", args.workers)

    # 解析高峰时间段
    peak_windows = parse_peak_windows(args.peak_windows)
    print(">>> peak windows:", peak_windows)

    # 读取文件
    _, ext = os.path.splitext(args.csv)
    ext = ext.lower()
    df_chunks = []

    if ext == ".csv":
        # csv 流式读取并切块
        reader = pd.read_csv(args.csv, encoding="gbk", chunksize=args.chunksize, low_memory=True, on_bad_lines="skip")
        for chunk in reader:
            chunk.columns = chunk.columns.str.strip()
            # 先过滤掉基本缺失列
            chunk = chunk.dropna(subset=[COL_DEP_LON, COL_DEP_LAT, COL_DEST_LON, COL_DEST_LAT, COL_DRIVE_MILE, COL_DRIVE_TIME])
            # 按时间列去高峰（如果指定）
            if args.time_col and peak_windows:
                chunk = filter_peak_hours_df(chunk, args.time_col, peak_windows)
            if len(chunk):
                df_chunks.append(chunk)
    else:
        print(">>> loading excel ... (read whole file into memory)")
        xls = pd.ExcelFile(args.csv)
        print("Sheets:", xls.sheet_names)
        df_all = pd.read_excel(args.csv, sheet_name=xls.sheet_names[0])
        df_all.columns = df_all.columns.str.strip()
        df_all = clean_xlsx_dataframe(df_all, time_col=args.time_col, peak_windows=peak_windows)

        # 分块
        for i in range(0, len(df_all), args.chunksize):
            df_chunks.append(df_all.iloc[i:i + args.chunksize].copy())

    print(">>> total chunks:", len(df_chunks))
    if len(df_chunks) == 0:
        print("❌ no data chunks to process")
        return

    params = dict(min_duration_s=args.min_duration_s, output_dir=args.output_dir)

    # 检查已处理的块
    processed_chunks = set()
    if os.path.exists(args.output_dir):
        for f in os.listdir(args.output_dir):
            if f.startswith("edge_chunk_") and f.endswith(".csv"):
                # 提取块编号
                try:
                    chunk_id = int(f.split("_")[-1].split(".")[0])
                    processed_chunks.add(chunk_id)
                except:
                    pass
    print(f">>> already processed chunks: {sorted(processed_chunks)}")

    # 动态调整进程数
    import multiprocessing
    num_cpus = multiprocessing.cpu_count()
    optimal_workers = min(num_cpus, args.workers)
    print(f">>> Using {optimal_workers} workers (detected {num_cpus} CPU cores)")

    # 并行处理（每个 worker 会执行 load_graph_worker）
    with ProcessPoolExecutor(max_workers=optimal_workers, initializer=load_graph_worker, initargs=(args.road_shp,)) as exe:
        futures = []
        for cid, chunk in enumerate(df_chunks):
            if cid in processed_chunks:
                print(f">>> chunk {cid} already processed, skipping")
                continue
            futures.append(exe.submit(process_chunk, chunk, cid, params))

        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                print("Worker raised exception:", e)

    print(">>> merging ...")
    files = [os.path.join(args.output_dir, f) for f in os.listdir(args.output_dir) if f.startswith("edge_chunk_")]
    if not files:
        print("❌ no edge output generated")
        return

    agg = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    final = agg.groupby(["u", "v"]).agg(
        tot_dist_m=("tot_dist_m", "sum"),
        tot_time_s=("tot_time_s", "sum"),
        cnt=("cnt", "sum")
    ).reset_index()

    final["avg_speed_kmh"] = final["tot_dist_m"] / 1000.0 / (final["tot_time_s"] / 3600.0)
    final["avg_speed_kmh"] = final["avg_speed_kmh"].clip(MIN_SPEED_KMH, MAX_SPEED_KMH)

    geoms = []
    for _, r in final.iterrows():
        # u/v 在 csv 中会是 "(x, y)" 字符串，或已是 tuple/list
        try:
            u = ast.literal_eval(r["u"])
            v = ast.literal_eval(r["v"])
        except Exception:
            if isinstance(r["u"], (list, tuple)):
                u = tuple(r["u"])
                v = tuple(r["v"])
            else:
                continue
        geoms.append(LineString([u, v]))

    gdf = gpd.GeoDataFrame(final, geometry=geoms, crs="EPSG:4326")
    out_shp = os.path.join(args.output_dir, "edge_speed_final.shp")
    gdf.to_file(out_shp)

    print("=== DONE ===")
    print(out_shp)


# ============================
if __name__ == "__main__":
    # ---------- 配置（直接写在代码里，替代命令行参数） ----------
# 如需修改，请在此处调整下列变量
    cfg = dict(
    csv=CSV_PATH,
    road_shp=ROAD_SHP,
    output_dir=OUTPUT_DIR,
    chunksize=CHUNKSIZE,
    workers=NUM_WORKERS,
    min_duration_s=MIN_DURATION_S,
    # 指明数据中的时间列名（用于高峰过滤），若为 None 则不做高峰过滤
    time_col='DEP_TIME',
    # 高峰时间段（逗号分隔），格式示例：'07:00-09:00,17:00-19:00'
    peak_windows='07:00-09:00,17:00-19:00'
    )

# 将 cfg 转为与之前 argparse 相同的对象传入 main
    args = argparse.Namespace(**cfg)

# 运行主流程
    main(args)