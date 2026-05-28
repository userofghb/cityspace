from cityseer.tools import io
from cityseer.metrics import layers,networks
import geopandas as gpd
import logging
import re
from pypinyin import pinyin, Style
from unidecode import unidecode
import networkx as nx
import numpy as np
from shapely import geometry, ops
from tqdm import tqdm
from cityseer import config
from cityseer.tools import util
from cityseer.tools.util import EdgeData, MultiGraph, NodeKey
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def clean_field_names(gdf):
    """
    清理 GeoDataFrame 的字段名，使其符合 Shapefile 格式要求（ASCII 字符），并避免重复字段名。
    """

    def chinese_to_pinyin(name):
        # 将中文转换为拼音
        return ''.join(p[0].capitalize() for p in pinyin(name, style=Style.NORMAL))

    def clean_name(name):
        # 如果包含中文字符，转换为拼音
        if re.search(r'[\u4e00-\u9fa5]', name):
            name = chinese_to_pinyin(name)
        # 将非字母、数字和下划线的字符替换为下划线
        name = re.sub(r'[^A-Za-z0-9_]', '_', name)
        # 转换为 ASCII 字符
        name = unidecode(name)
        # 限制字段名长度为10个字符
        return name[:10]

    # 批量清理所有字段名，并处理重复字段名
    seen = {}
    new_columns = {}
    for col in gdf.columns:
        clean_col = clean_name(col)
        # 如果生成的字段名已经存在，添加一个后缀使其唯一
        while clean_col in seen:
            seen[clean_col] += 1
            clean_col = f"{clean_col[:8]}_{seen[clean_col]}"
        seen[clean_col] = 0
        new_columns[col] = clean_col

    gdf = gdf.rename(columns=new_columns)

    # 创建一个新的 GeoDataFrame 来减少碎片化
    gdf = gdf.copy()

    return gdf
def my_nx_decompose(nx_multigraph: MultiGraph, decompose_max: float) -> MultiGraph:

    if not isinstance(nx_multigraph, nx.MultiGraph):
        raise TypeError("This method requires an undirected networkX MultiGraph.")
    logger.info(f"Decomposing graph to maximum edge lengths of {decompose_max}.")
    g_multi_copy: MultiGraph = nx_multigraph.copy()

    start_nd_key: NodeKey
    end_nd_key: NodeKey
    edge_data: EdgeData

    for start_nd_key, end_nd_key, edge_data in tqdm(nx_multigraph.edges(data=True), disable=config.QUIET_MODE):
        # test for x, y in start coordinates
        if "x" not in nx_multigraph.nodes[start_nd_key] or "y" not in nx_multigraph.nodes[start_nd_key]:
            raise KeyError(f'Encountered node missing "x" or "y" coordinate attributes at node {start_nd_key}.')

        # test for x, y in end coordinates
        if "x" not in nx_multigraph.nodes[end_nd_key] or "y" not in nx_multigraph.nodes[end_nd_key]:
            raise KeyError(f'Encountered node missing "x" or "y" coordinate attributes at node {end_nd_key}.')

        # test for geom
        if "geom" not in edge_data:
            raise KeyError(
                f"No edge geom found for edge {start_nd_key}-{end_nd_key}: Please add an edge 'geom' attribute consisting of a shapely LineString.")

        # get edge geometry
        line_geom: geometry.LineString = edge_data["geom"]
        if line_geom.geom_type != "LineString":
            raise TypeError(
                f"Expected LineString geometry but found {line_geom.geom_type} for edge {start_nd_key}-{end_nd_key}.")

        # check geom coordinates directionality - flip if facing backwards direction
        line_geom_coords = util.snap_linestring_endpoints(nx_multigraph, start_nd_key, end_nd_key, line_geom.coords)
        line_geom: geometry.LineString = geometry.LineString(line_geom_coords)

        # see how many segments are necessary so as not to exceed decomposition max distance
        cuts: int = int(np.ceil(line_geom.length / decompose_max))
        step_size: float = line_geom.length / cuts

        # since decomposing, remove the prior edge... but only after properties have been read
        g_multi_copy.remove_edge(start_nd_key, end_nd_key)

        # then add the new sub-edge/s
        step = 0
        prior_node_id = start_nd_key
        sub_node_counter = 0

        for _ in range(cuts - 1):
            # create the split LineString geom for measuring the new length
            line_segment: geometry.LineString = ops.substring(line_geom, step, step + step_size)

            # get the x, y of the new end node
            x, y = line_segment.coords[-1]

            # Check if the node already exists, if so, skip adding it
            if g_multi_copy.has_node((x, y)):
                raise ValueError(
                    f"Attempted to add a duplicate node at x: {x}, y:{y}. "
                    f"Check for existence of duplicate edges in the vicinity of {start_nd_key}-{end_nd_key}."
                )

            # add the new node and edge
            new_nd_name, is_dupe = util.add_node(g_multi_copy, [start_nd_key, sub_node_counter, end_nd_key], x=x, y=y)

            # Proceed if the node is not a duplicate
            if not is_dupe:
                sub_node_counter += 1

                # Add live property if present in parent graph
                if "live" in nx_multigraph.nodes[start_nd_key] and "live" in nx_multigraph.nodes[end_nd_key]:
                    live = True
                    if not nx_multigraph.nodes[start_nd_key]["live"] and not nx_multigraph.nodes[end_nd_key]["live"]:
                        live = False
                    g_multi_copy.nodes[new_nd_name]["live"] = live

                # Add the edge
                edge_data_copy = {k: v for k, v in edge_data.items() if k != "geom"}
                g_multi_copy.add_edge(prior_node_id, new_nd_name, geom=line_segment, **edge_data_copy)

                prior_node_id = new_nd_name
                step += step_size

        # Set the last edge manually to avoid rounding errors at end of LineString
        line_segment = ops.substring(line_geom, step, line_geom.length)
        edge_data_copy = {k: v for k, v in edge_data.items() if k != "geom"}
        g_multi_copy.add_edge(prior_node_id, end_nd_key, geom=line_segment, **edge_data_copy)

    return g_multi_copy
df_streets: gpd.GeoDataFrame = gpd.read_file('D:/2024srtp/road/newroad/zcqroad.shp', layer="zcqroad")
#录入为gdf
df_streets = df_streets.to_crs(epsg=32650)
df_streets = df_streets.explode(ignore_index=True)#拆开mulitgeometries
nx_momepy = io.nx_from_generic_geopandas(df_streets)#转换为muiltgraph
data_gdf: gpd.GeoDataFrame=gpd.read_file('D:/2024srtp/poi/主城区poi.shp', layer="主城区poi")
data_gdf = data_gdf.to_crs(epsg=32650)
# 清理字段名
data_gdf = clean_field_names(data_gdf)
data_gdf = data_gdf.reset_index(level=0, drop=True)
data_gdf.index = data_gdf.index.astype(str)

unique_main_tags = data_gdf['main_tag'].drop_duplicates().tolist()
# 打印所有唯一标签
print(unique_main_tags)
unique_main_tags=['购物', '金融', '房地产', '公司企业', '美食', '政府机构', '酒店', '生活服务',
                  '教育培训', '文体传媒', '医疗', '交通设施', '丽人', '旅游景点', '休闲娱乐', '运动健身']

clipped_momepy = my_nx_decompose(nx_momepy, 15)  # 调整分解粒度
#分解成点
nodes_gdf, edges_gdf, network_structure = io.network_structure_from_nx(clipped_momepy, crs=32650)

distances = [50,100,200,400]

#中心性计算
nodes_gdf = networks.node_centrality_shortest(
    network_structure=network_structure,  # the network structure for which to compute the measures
    nodes_gdf=nodes_gdf,  # the nodes GeoDataFrame, to which the results will be written
    distances=distances,
)
#计算mixed_use
nodes_gdf, data_gdf = layers.compute_mixed_uses(
    data_gdf,  # the source data
    landuse_column_label="main_tag",  # column in the dataframe which contains the landuse labels
    nodes_gdf=nodes_gdf,  # nodes GeoDataFrame - the results are written here
    network_structure=network_structure,  # measures will be computed relative to pedestrian distances over the network
    distances=distances,# distance thresholds for which you want to compute the measures
)

nodes_gdf, pubs_data_gdf = layers.compute_accessibilities(
    data_gdf,
    landuse_column_label="main_tag",
    accessibility_keys=unique_main_tags,
    nodes_gdf=nodes_gdf,
    network_structure=network_structure,
    distances=distances,
)
# Compute mixed uses and update node_gdf
nodes_gdf=clean_field_names(nodes_gdf)
# 输出为GPKG格式，保持字段名不超过10个字符的限制
nodes_gdf.to_file('D:/2024srtp/finalresult/allcity/prepare.gpkg', driver='GPKG')
logger.info("输出完成，使用GPKG格式，字段名已限制在10个字符以内")