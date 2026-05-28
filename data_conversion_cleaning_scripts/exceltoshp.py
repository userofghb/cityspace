import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# ---------- Step 1：读取 CSV，尝试多种编码 ----------
file_path = "C:/Users/27462/Desktop/2024srtp/nanjing10m2_yolo_4090/final_detection_results.csv"

# 尝试不同的编码
encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1', 'cp1252', 'iso-8859-1']

for encoding in encodings:
    try:
        df = pd.read_csv(file_path, encoding=encoding)
        print(f"成功使用 {encoding} 编码读取文件")
        break
    except UnicodeDecodeError:
        print(f"{encoding} 编码失败，尝试下一个...")
        continue
else:
    # 如果所有编码都失败，尝试用二进制读取并检测
    import chardet

    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
        detected_encoding = result['encoding']
        print(f"检测到的编码: {detected_encoding}, 置信度: {result['confidence']}")

    try:
        df = pd.read_csv(file_path, encoding=detected_encoding)
        print(f"成功使用检测到的编码 {detected_encoding} 读取文件")
    except:
        print("所有编码尝试都失败，请手动检查文件编码")
        exit()

# ---------- Step 2：显示前几行和列名，确认数据结构 ----------
print("\n数据预览:")
print(df.head())
print("\n列名:")
print(df.columns.tolist())

# ---------- Step 3：检查是否有经纬度列 ----------
# 查找可能的经纬度列名
print("\n查找经纬度列...")
lon_candidates = [col for col in df.columns if any(word in col.lower() for word in ['lon', 'lng', 'longitude', '经度'])]
lat_candidates = [col for col in df.columns if any(word in col.lower() for word in ['lat', 'latitude', '纬度'])]

print(f"可能的经度列: {lon_candidates}")
print(f"可能的纬度列: {lat_candidates}")

# 如果没有自动找到，手动指定
if not lon_candidates or not lat_candidates:
    print("请从上面的列名中选择经纬度列:")
    print(df.columns.tolist())

    # 你可以在这里手动指定列名
    lon_col = 'lng'  # 修改为你的经度列名
    lat_col = 'lat'  # 修改为你的纬度列名
else:
    lon_col = lon_candidates[0]
    lat_col = lat_candidates[0]

print(f"使用经度列: {lon_col}")
print(f"使用纬度列: {lat_col}")

# ---------- Step 4：检查数据类型 ----------
print(f"\n{lon_col} 数据类型: {df[lon_col].dtype}")
print(f"{lat_col} 数据类型: {df[lat_col].dtype}")

# 如果经纬度列是字符串，尝试转换为数值
for col in [lon_col, lat_col]:
    if df[col].dtype == object:
        try:
            df[col] = pd.to_numeric(df[col])
            print(f"已将 {col} 转换为数值类型")
        except:
            print(f"警告: {col} 无法转换为数值类型")

# ---------- Step 5：创建 geometry ----------
try:
    # 删除经纬度为空的行
    df_clean = df.dropna(subset=[lon_col, lat_col])
    print(f"\n原始数据行数: {len(df)}")
    print(f"清理后数据行数: {len(df_clean)}")

    geometry = [Point(xy) for xy in zip(df_clean[lon_col], df_clean[lat_col])]

    # ---------- Step 6：构建 GeoDataFrame ----------
    gdf = gpd.GeoDataFrame(df_clean, geometry=geometry, crs="EPSG:4326")

    # ---------- Step 7：导出为 shapefile ----------
    output_path = "C:/Users/27462/Desktop/2024srtp/nanjing10m2_yolo_4090/image.shp"
    gdf.to_file(output_path, driver="ESRI Shapefile", encoding="utf-8")
    print(f"\nShapefile 已成功导出到: {output_path}")

except Exception as e:
    print(f"处理过程中出错: {e}")
    print("\n数据样本:")
    print(df[[lon_col, lat_col]].head())