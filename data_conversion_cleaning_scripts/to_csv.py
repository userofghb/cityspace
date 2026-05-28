import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import chardet
csv_path = r"C:/Users/27462/Desktop/2024srtp/拱墅数据_给srtp/POI/浙江省_杭州市_百度poi_筛选.csv"
shp_path = r"C:/Users/27462/Desktop/2024srtp/拱墅数据_给srtp/POI/poi.shp"

lon_col = "WGS84_lon"
lat_col = "WGS84_lat"

# =======================
# 第一步：自动检测编码
# =======================
with open(csv_path, "rb") as f:
    raw = f.read()
detected = chardet.detect(raw)
encoding = detected["encoding"]
print("检测到编码：", encoding)

# =======================
# 第二步：用 replace 解码（不报错）
# =======================
text = raw.decode(encoding, errors="replace")

# =======================
# 第三步：把解码后的文本喂给 pandas
# =======================
from io import StringIO
df = pd.read_csv(StringIO(text))

# =======================
# 转 GeoDataFrame
# =======================
gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
    crs="EPSG:4326"
)

gdf.to_file(shp_path, encoding="utf-8")
print("成功输出 SHP:", shp_path)
