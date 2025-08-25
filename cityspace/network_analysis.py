# spatialflow/network_analysis.py

import geopandas as gpd
from cityseer.tools import io, networks, layers
from spatialflow.preprocess import clean_field_names，my_nx_decompose

def process_network_analysis(
    streets_path: str,
    poi_path: str,
    poi_label: str,
    output_path: str,
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
        output_path: 输出节点 shapefile 路径
        epsg: 坐标参考系
        decompose_granularity: 网络分解粒度
        distance_thresholds: 中心性和可达性计算距离列表
        count_centrality:是否计算中心性
        count_mixed_uses:是否计算复杂程度
        count_accessibilities:是否计算可达性
    返回:
        nodes_gdf: 节点 GeoDataFrame
        edges_gdf: 边 GeoDataFrame
        network_structure: 网络结构
    """
    if distance_thresholds is None:
        distance_thresholds = [25, 50, 100, 200]

    # 读取街道数据
    df_streets: gpd.GeoDataFrame = gpd.read_file(streets_path)
    df_streets = df_streets.to_crs(epsg=epsg)
    df_streets = df_streets.explode(ignore_index=True)
    nx_momepy = io.nx_from_generic_geopandas(df_streets)

    # 读取POI数据
    data_gdf: gpd.GeoDataFrame = gpd.read_file(poi_path)
    data_gdf = data_gdf.to_crs(epsg=epsg)
    data_gdf = clean_field_names(data_gdf)
    data_gdf = data_gdf.reset_index(level=0, drop=True)
    data_gdf.index = data_gdf.index.astype(str)

    unique_main_tags = data_gdf[poi_label].drop_duplicates().tolist()
    print("Unique main tags:", unique_main_tags)

    # 网络分解
    clipped_momepy = my_nx_decompose(nx_momepy, decompose_granularity)
    nodes_gdf, edges_gdf, network_structure = io.network_structure_from_nx(clipped_momepy, crs=epsg)

    # 中心性计算
    nodes_gdf = networks.node_centrality_shortest(
        network_structure=network_structure,
        nodes_gdf=nodes_gdf,
        distances=distance_thresholds,
    )

    # 计算混合用途
    nodes_gdf, data_gdf = layers.compute_mixed_uses(
        data_gdf,
        landuse_column_label=poi_label,
        nodes_gdf=nodes_gdf,
        network_structure=network_structure,
        distances=distance_thresholds,
    )

    # 可达性计算
    nodes_gdf, pubs_data_gdf = layers.compute_accessibilities(
        data_gdf,
        landuse_column_label=poi_label,
        accessibility_keys=unique_main_tags,
        nodes_gdf=nodes_gdf,
        network_structure=network_structure,
        distances=distance_thresholds,
    )

    nodes_gdf = clean_field_names(nodes_gdf)

    # 保存结果
    nodes_gdf.to_file(output_path, driver='ESRI Shapefile')

    return nodes_gdf, edges_gdf, network_structure
