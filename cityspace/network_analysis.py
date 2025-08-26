# spatialflow/network_analysis.py

import geopandas as gpd
from cityseer.tools import io, networks, layers
import cityspace.tools as mytools
import pandas as pd
import logging

def process_poi_network_analysis(
    streets_path: str,
    poi_path: str,
    poi_label: str,
    epsg: int = 32650,
    decompose_granularity: int,
    distance_thresholds=None,
    count_centrality=True,
    count_mixed_uses=True,
    count_accessibilities=True
):
    """
    从街道和POI数据生成节点、边、网络结构，并计算中心性、混合用途、可达性。

    参数:
        streets_path: 街道 shapefile 路径
        poi_path: POI shapefile 路径
        poi_label: POI数据的类型标签
        myepsg: 期望坐标参考系
        decompose_granularity: 网络分解粒度
        distance_thresholds: 中心性和可达性计算距离列表
        count_centrality:是否计算中心性
        count_mixed_uses:是否计算复杂程度
        count_accessibilities:是否计算可达性
    返回:
        nodes_gdf: 处理后节点 GeoDataFrame
        edges_gdf: 道路边 GeoDataFrame
        network_structure: 道路网络结构
    """
    if distance_thresholds is None:
        distance_thresholds = [25, 50, 100, 200]

    # 读取街道数据
    df_streets: gpd.GeoDataFrame = gpd.read_file(streets_path)
    df_streets = df_streets.to_crs(epsg=myepsg)
    df_streets = df_streets.explode(ignore_index=True)
    nx_momepy = io.nx_from_generic_geopandas(df_streets)

    # 读取POI数据
    data_gdf: gpd.GeoDataFrame = gpd.read_file(poi_path)
    data_gdf = data_gdf.to_crs(epsg=myepsg)
    data_gdf = mytools.clean_field_names(data_gdf)
    data_gdf = data_gdf.reset_index(level=0, drop=True)
    data_gdf.index = data_gdf.index.astype(str)

    unique_main_tags = data_gdf[poi_label].drop_duplicates().tolist()
    print("Unique main tags:", unique_main_tags)

    # 网络分解
    clipped_momepy = mytools.my_nx_decompose(nx_momepy, decompose_granularity)
    nodes_gdf, edges_gdf, network_structure = io.network_structure_from_nx(clipped_momepy, crs=myepsg)

    # 中心性计算
    if count_centrality:
        nodes_gdf = networks.node_centrality_shortest(
            network_structure=network_structure,
            nodes_gdf=nodes_gdf,
            distances=distance_thresholds,
        )

    # 计算混合用途
    if count_mixed_uses:
        nodes_gdf, data_gdf = layers.compute_mixed_uses(
            data_gdf,
            landuse_column_label=poi_label,
            nodes_gdf=nodes_gdf,
            network_structure=network_structure,
            distances=distance_thresholds,
        )

    # 可达性计算
    if count_accessibilities:
        nodes_gdf, pubs_data_gdf = layers.compute_accessibilities(
            data_gdf,
            landuse_column_label=poi_label,
            accessibility_keys=unique_main_tags,
            nodes_gdf=nodes_gdf,
            network_structure=network_structure,
            distances=distance_thresholds,
        )

    nodes_gdf = clean_field_names(nodes_gdf)

    return nodes_gdf, edges_gdf, network_structure
def process_streetpic_network_analysis(
    road_path: str,
    target_path: str,
    buffer_radii = None  # 单位：米
    myepsg: int = 32650
    type_field: str
    value_field: str
):"""
    使用以完备的道路点和街景进行统计运算。

    参数:
        road_path: 道路点shapefile路径,
        target_path: 街景shapefile路径,
        buffer_radii：搜索范围
        myepsg: 期望参考坐标系
        type_field: 类型列名
        value_field: 类型数目列名
    返回:
        roads: 处理后街道点
    """
    # ---------- 日志 ----------
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if buffer_radii is None:
        buffer_radii=[50,100,200]
    # ---------- 读数据 ----------
    roads = gpd.read_file(road_path).to_crs(epsg=myepsg)  # 转换为米坐标系（UTM）
    targets = gpd.read_file(target_path).to_crs(epsg=myepsg)
    
    # 确保 num 列是整数
    targets[value_field] = pd.to_numeric(targets[value_field], errors="coerce").fillna(0).astype(int)
    
    # 确保几何有效
    targets = targets[targets.is_valid].copy()
    
    # 提取所有类别
    all_types = targets[type_field].dropna().unique()
    
    # ---------- 批量处理 ----------
    for radius in buffer_radii:
        logging.info(f"开始处理半径 {radius} m ...")
    
        # 复制 roads，生成 buffer
        buffers = roads[["geometry"]].copy()
        buffers["geometry"] = buffers.geometry.buffer(radius)
        buffers["road_id"] = buffers.index
    
        # 空间连接（目标点 → buffer）
        joined = gpd.sjoin(buffers, targets, predicate="intersects")
    
        logging.info(f"半径 {radius} m 匹配到 {len(joined)} 个点")
    
        # 如果没有匹配结果，跳过
        if joined.empty:
            continue
    
        # 按道路点和 type 聚合
        agg_df = joined.groupby(["road_id", type_field])[value_field].sum().reset_index()
    
        # 生成透视表（行=road_id，列=type，值=统计和）
        pivot_df = agg_df.pivot(index="road_id", columns=type_field, values=value_field).reindex(columns=all_types, fill_value=0)
    
        # 列名改成 sum_xxx_radius
        pivot_df.columns = [f"sum_{t}_{radius}" for t in pivot_df.columns]
        pivot_df = pivot_df.reset_index()
    
        # 合并结果到原始 roads
        roads = roads.merge(pivot_df, left_index=True, right_on="road_id", how="left").drop(columns="road_id")
    
    # ---------- 保存 ----------
    logging.info("处理完成")
    return roads
    
        
