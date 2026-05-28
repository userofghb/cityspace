import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Point
import re

# =====================================================
# 1. 参数配置（直接在这里改路径）
# =====================================================
ROADS_SHP = r"D:/2024srtp/product3/linkn3.shp"          # 道路点 shp
CHECKINS_CSV = r"D:/2024srtp/1225 主城微博/1225 weibo.csv"  # 打卡 CSV
OUTPUT_SHP = r"D:/2024srtp/product3/linkn4.shp"        # 输出 shp
MAX_DIST = 50                                         # 最近邻匹配距离（米）

# Shapefile 字段名（<=10 字符）
SLOT_FIELDS = ["wk_all", "we_all"]

# =====================================================
# 2. 工具函数
# =====================================================
def find_lon_lat(df):
    """自动识别经纬度列"""
    lon_keys = ["经度", "lng", "longitude", "x"]
    lat_keys = ["纬度", "latitude", "y"]
    lon = lat = None
    for c in df.columns:
        if c.lower() in lon_keys and lon is None:
            lon = c
        if c.lower() in lat_keys and lat is None:
            lat = c
    return lon, lat


def find_time_col(df):
    """自动识别时间列"""
    for c in df.columns:
        if re.search(r"发布时", c, re.I):
            return c
    return df.columns[0]


def time_slot(dt):
    """时间 → 周中 / 周末"""
    if pd.isna(dt):
        return None
    weekday = dt.weekday()  # 周一=0
    return "wk" if weekday <= 4 else "we"


def detect_encoding(filepath, sample_bytes=200000):
    """自动检测 CSV 编码"""
    try:
        import chardet
    except Exception:
        return None
    with open(filepath, "rb") as f:
        raw = f.read(sample_bytes)
    if not raw:
        return None
    res = chardet.detect(raw)
    return res.get("encoding")

# =====================================================
# 3. 读取道路点
# =====================================================
roads = gpd.read_file(ROADS_SHP)

if roads.crs is None:
    roads.set_crs(epsg=4326, inplace=True)

# 显式生成道路 ID（不使用 index）
roads["rid"] = roads.index.astype(int)

roads_m = roads.to_crs(epsg=3857)

# =====================================================
# 4. 读取并清洗打卡 CSV
# =====================================================
enc = detect_encoding(CHECKINS_CSV)
print("检测到编码（可能）：", enc)

df = None
read_success = False

if enc:
    try:
        df = pd.read_csv(CHECKINS_CSV, encoding=enc,
                         engine="python", encoding_errors="ignore")
        read_success = True
        print(f"使用检测编码读取成功：{enc}")
    except Exception as e:
        print(f"检测编码读取失败：{e}")

if not read_success:
    for trial_enc in ["utf-8", "gbk", "gb18030", "latin1"]:
        try:
            df = pd.read_csv(CHECKINS_CSV, encoding=trial_enc,
                             engine="python", encoding_errors="ignore")
            print(f"回退并成功使用编码：{trial_enc}")
            break
        except Exception:
            pass

if df is None:
    raise RuntimeError("CSV 读取失败，请检查文件编码或路径")

lon_col, lat_col = find_lon_lat(df)
time_col = find_time_col(df)

df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
df = df.dropna(subset=[lon_col, lat_col])

# 时间解析（兼容 2024/12/15 4:49 等格式）
df["dt"] = pd.to_datetime(
    df[time_col],
    format="%Y/%m/%d %H:%M",
    errors="coerce"
)
df["dt"] = df["dt"].fillna(pd.to_datetime(df[time_col], errors="coerce"))

# 构造 GeoDataFrame
g_check = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
    crs="EPSG:4326"
).to_crs(epsg=3857)

# =====================================================
# 5. 最近邻匹配（道路点）
# =====================================================
matched = gpd.sjoin_nearest(
    g_check,
    roads_m[["rid", "geometry"]],
    how="left",
    max_distance=MAX_DIST,
    distance_col="dist"
)

matched = matched.dropna(subset=["rid"])

# =====================================================
# 6. 周中 / 周末统计 （修正版）
# =====================================================
matched["slot"] = matched["dt"].apply(time_slot)
matched = matched.dropna(subset=["slot"])

stat = (
    matched
    .groupby(["rid", "slot"])
    .size()
    .unstack(fill_value=0)
)

# 把 'wk'/'we' 重命名为输出字段 'wk_only'/'we_only'（如果存在）
col_map = {}
if "wk" in stat.columns:
    col_map["wk"] = "wk_all"
if "we" in stat.columns:
    col_map["we"] = "we_all"
if col_map:
    stat = stat.rename(columns=col_map)

# 补齐输出字段（如果某个字段完全没出现则补 0）
for f in SLOT_FIELDS:
    if f not in stat.columns:
        stat[f] = 0

# 保证列顺序且把 rid 从索引变为列
stat = stat.reset_index()[["rid"] + SLOT_FIELDS]

# =====================================================
# 7. 合并回道路点（保持不变）
# =====================================================
roads_out = roads_m.merge(stat, on="rid", how="left")

for f in SLOT_FIELDS:
    roads_out[f] = roads_out[f].fillna(0).astype(int)

roads_out = roads_out.to_crs(roads.crs)


# =====================================================
# 7. 合并回道路点
# =====================================================
roads_out = roads_m.merge(stat, on="rid", how="left")

for f in SLOT_FIELDS:
    roads_out[f] = roads_out[f].fillna(0).astype(int)

roads_out = roads_out.to_crs(roads.crs)

# =====================================================
# 8. 输出 SHP
# =====================================================
roads_out.to_file(OUTPUT_SHP, encoding="utf-8")
print("处理完成，结果已保存为：", OUTPUT_SHP)
