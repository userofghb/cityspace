import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')


def calculate_hill_numbers(series, q_values=[0, 1, 2]):
    """
    计算Hill numbers多样性指数

    参数:
    series: pandas Series，每个元素是一个类别的值（存在与否或计数）
    q_values: 要计算的q值列表

    返回:
    dict: 包含每个q值对应的多样性指数
    """
    # 过滤掉值为0或NaN的类别
    valid_data = series[series > 0].dropna()

    if len(valid_data) == 0:
        return {f'q{q}': 0 for q in q_values}

    # 计算每个类别的比例
    proportions = valid_data / valid_data.sum()

    # 将proportions转换为numpy数组以避免pandas Series的log问题
    proportions_array = proportions.values.astype(float)

    results = {}

    for q in q_values:
        if q == 0:
            # q=0: 丰富度（Richness）
            results[f'q{q}'] = len(valid_data)

        elif q == 1:
            # q=1: 指数化香农熵
            # 只计算大于0的部分，避免log(0)
            mask = proportions_array > 0
            if mask.any():
                # 使用numpy计算，避免pandas Series的问题
                valid_proportions = proportions_array[mask]
                shannon = -np.sum(valid_proportions * np.log(valid_proportions))
                results[f'q{q}'] = np.exp(shannon) if not np.isinf(shannon) and not np.isnan(shannon) else 1.0
            else:
                results[f'q{q}'] = 1.0

        elif q == 2:
            # q=2: 辛普森多样性的倒数
            simpson = np.sum(proportions_array ** 2)
            results[f'q{q}'] = 1 / simpson if simpson > 0 else 0

        else:
            # 通用Hill number公式
            if q == 1:
                # 已经处理过q=1的情况
                continue
            else:
                try:
                    D_q = np.sum(proportions_array ** q) ** (1 / (1 - q))
                    results[f'q{q}'] = D_q if not np.isinf(D_q) and not np.isnan(D_q) else 0
                except:
                    results[f'q{q}'] = 0

    return results


def calculate_diversity_for_dataframe(df, method='exclude'):
    """
    为整个DataFrame计算多样性指数

    参数:
    df: pandas DataFrame，包含image列和其他标签列
    method: 'exclude'（排除车辆类）或 'combine'（合并车辆类为一类）

    返回:
    DataFrame: 包含image列和多样性指数的结果
    """
    # 原始标签列（排除image列）
    all_columns = df.columns.tolist()
    label_columns = [col for col in all_columns if col != 'image']

    # 确保所有标签列都是数值类型
    for col in label_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 要排除的非车辆标签
    exclude_non_vehicle = ['rail track', 'tunnel', 'pothole', 'boat', 'on rails', 'trailer', 'truck', 'unlabeled']

    # 车辆类标签
    vehicle_labels = ['bus', 'car', 'caravan', 'motorcycle', 'other vehicle',
                      'wheeled slow', 'car mount', 'ego vehicle']

    # 准备要计算的标签列
    if method == 'exclude':
        # 排除所有指定的标签（包括非车辆和车辆）
        excluded = exclude_non_vehicle + vehicle_labels
        calc_columns = [col for col in label_columns if col not in excluded]

    elif method == 'combine':
        # 排除非车辆标签，但合并车辆标签
        # 首先排除非车辆标签
        calc_columns_non_vehicle = [col for col in label_columns if col not in exclude_non_vehicle]

        # 创建一个新的DataFrame来存储处理后的数据
        processed_data = []

        # 对于每一行，计算车辆类的合并值
        for idx, row in df.iterrows():
            # 非车辆类标签的值
            non_vehicle_vals = {}
            for col in calc_columns_non_vehicle:
                if col not in vehicle_labels and col != 'image':
                    non_vehicle_vals[col] = float(row[col])  # 确保是float类型

            # 计算车辆类的合并值
            vehicle_sum = 0
            for vehicle in vehicle_labels:
                if vehicle in df.columns:
                    vehicle_sum += float(row[vehicle])

            # 如果有至少一个车辆类标签有值，则设置为1，否则为0
            vehicle_val = 1.0 if vehicle_sum > 0 else 0.0

            # 合并所有值
            all_vals = non_vehicle_vals.copy()
            all_vals['vehicle_combined'] = vehicle_val
            all_vals['image'] = row['image']

            processed_data.append(all_vals)

        # 创建新的DataFrame
        processed_df = pd.DataFrame(processed_data)

        # 直接使用处理后的DataFrame计算多样性
        result_list = []

        for idx, row in processed_df.iterrows():
            # 提取标签值（排除image列）
            label_values = row.drop('image')
            diversity = calculate_hill_numbers(label_values)

            result = {'image': row['image']}
            result.update({f'method_combine_{k}': v for k, v in diversity.items()})
            result_list.append(result)

        return pd.DataFrame(result_list)

    else:
        raise ValueError("method参数必须是'exclude'或'combine'")

    # 对于exclude方法，直接计算
    result_list = []

    for idx, row in df.iterrows():
        # 提取要计算的列
        label_values = row[calc_columns]
        diversity = calculate_hill_numbers(label_values)

        result = {'image': row['image']}
        result.update({f'method_exclude_{k}': v for k, v in diversity.items()})
        result_list.append(result)

    return pd.DataFrame(result_list)


# 主程序
def main():
    # 1. 读取CSV文件（请根据实际文件路径修改）
    file_path = 'C:/Users/27462/Desktop/2024srtp/nanjing10m.csv'  # 请替换为实际文件路径

    try:
        df = pd.read_csv(file_path)
        print(f"成功读取文件，数据形状: {df.shape}")
        print(f"列名: {df.columns.tolist()}")
    except Exception as e:
        print(f"读取文件时出错: {e}")
        print("请检查文件路径是否正确。")
        return None

    # 确保有image列
    if 'image' not in df.columns:
        print("警告：未找到'image'列，将使用索引作为image标识")
        df['image'] = df.index.astype(str)

    # 2. 计算两种方法的多样性
    print("\n计算排除车辆类的多样性...")
    try:
        exclude_results = calculate_diversity_for_dataframe(df, method='exclude')
        print(f"排除方法计算结果形状: {exclude_results.shape}")
    except Exception as e:
        print(f"计算排除方法时出错: {e}")
        exclude_results = pd.DataFrame()

    print("\n计算合并车辆类的多样性...")
    try:
        combine_results = calculate_diversity_for_dataframe(df, method='combine')
        print(f"合并方法计算结果形状: {combine_results.shape}")
    except Exception as e:
        print(f"计算合并方法时出错: {e}")
        combine_results = pd.DataFrame()

    # 3. 合并两种方法的结果
    if not exclude_results.empty and not combine_results.empty:
        if 'image' in exclude_results.columns and 'image' in combine_results.columns:
            # 使用merge合并
            final_results = pd.merge(exclude_results, combine_results, on='image', how='outer')
        else:
            # 如果image列名不同，使用concat
            final_results = pd.concat([exclude_results, combine_results], axis=1)
    elif not exclude_results.empty:
        final_results = exclude_results
        print("警告：只获取到排除方法的结果")
    elif not combine_results.empty:
        final_results = combine_results
        print("警告：只获取到合并方法的结果")
    else:
        print("错误：两种方法都计算失败")
        return None

    # 4. 输出结果
    output_file = 'C:/Users/27462/Desktop/2024srtp/nanjing10hill.csv'
    final_results.to_csv(output_file, index=False)
    print(f"\n多样性计算结果已保存到: {output_file}")

    # 5. 显示结果概览
    print("\n结果概览：")
    print(f"总样本数: {len(final_results)}")
    print("\n列名:")
    print(final_results.columns.tolist())

    # 显示前几行
    print("\n前5行结果:")
    print(final_results.head())

    # 统计摘要
    print("\n多样性指数统计摘要:")
    diversity_cols = [col for col in final_results.columns if 'q0' in col or 'q1' in col or 'q2' in col]
    if diversity_cols:
        print(final_results[diversity_cols].describe())
    else:
        print("未找到多样性指数列")

    return final_results


# 运行主程序
if __name__ == "__main__":
    # 执行计算
    results = main()

    if results is not None:
        # 保存详细统计信息
        try:
            stats_summary = results.describe().T
            stats_summary.to_csv('C:/Users/27462/Desktop/2024srtp/diversity_statistics_summary.csv')
            print("\n详细统计信息已保存到: diversity_statistics_summary.csv")
        except Exception as e:
            print(f"保存统计信息时出现错误: {e}")
    else:
        print("计算失败，请检查错误信息。")