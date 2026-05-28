# calc_street_indices.py
import pandas as pd
import numpy as np

# ---------- 配置 ----------
INPUT_CSV = "D:/2024srtp/result1/f.csv"       # 改成你的文件名
OUTPUT_CSV = "D:/2024srtp/result1/output.csv"
NORMALIZE_BY_ROW = True      # 是否先把 vegetation/sky_mean/building_m/sidewalk_m 归一为行内比例
EPS = 1e-4                   # 平滑项，避免 ln(0)

# ---------- 读取 CSV ----------
df = pd.read_csv(INPUT_CSV)

# 支持大小写容错，找到对应列名
expected_cols = ["vegetation", "sky_mean", "building_m", "sidewalk_m"]
col_map = {}
for col in expected_cols:
    matches = [c for c in df.columns if c.lower() == col]
    if not matches:
        raise KeyError(f"CSV 中缺少必须列: {col}（大小写敏感，或请确认列名正确）")
    col_map[col] = matches[0]  # 使用原始列名

# 取出列并确保为数值
veg = pd.to_numeric(df[col_map["vegetation"]], errors="coerce").fillna(0).astype(float)
sky = pd.to_numeric(df[col_map["sky_mean"]], errors="coerce").fillna(0).astype(float)
bld = pd.to_numeric(df[col_map["building_m"]], errors="coerce").fillna(0).astype(float)
swk = pd.to_numeric(df[col_map["sidewalk_m"]], errors="coerce").fillna(0).astype(float)

# ---------- 可选：按行归一化为比例 ----------
if NORMALIZE_BY_ROW:
    total = veg + sky + bld + swk
    # 若 total 为 0，保持原样（全部置 0），并避免除 0
    nonzero = total != 0
    veg_prop = veg.copy()
    sky_prop = sky.copy()
    bld_prop = bld.copy()
    swk_prop = swk.copy()
    veg_prop[nonzero] = veg[nonzero] / total[nonzero]
    sky_prop[nonzero] = sky[nonzero] / total[nonzero]
    bld_prop[nonzero] = bld[nonzero] / total[nonzero]
    swk_prop[nonzero] = swk[nonzero] / total[nonzero]
else:
    veg_prop = veg
    sky_prop = sky
    bld_prop = bld
    swk_prop = swk

# 为数值稳定性，保证非负（如果你的数据可能为负，可根据实际情况调整）
veg_prop = veg_prop.clip(lower=0.0)
sky_prop = sky_prop.clip(lower=0.0)
bld_prop = bld_prop.clip(lower=0.0)
swk_prop = swk_prop.clip(lower=0.0)

# ---------- 计算指标（按前面约定的简化公式） ----------
eps = EPS

# PPI = ln( (sidewalk + eps) / (sidewalk + building + vegetation + eps) )
PPI = np.log( (swk_prop + eps) / (swk_prop + bld_prop + veg_prop + eps) )

# EBI = ln( (building + vegetation + eps) / (building + vegetation + sky + sidewalk + eps) )
EBI = np.log( (bld_prop + veg_prop + eps) / (bld_prop + veg_prop + sky_prop + swk_prop + eps) )

# GGR = ln( (vegetation + eps) / (vegetation + building + sidewalk + eps) )
GGR = np.log( (veg_prop + eps) / (veg_prop + bld_prop + swk_prop + eps) )

# ---------- 把结果写回 DataFrame ----------
df_out = df.copy()
# 若进行了归一化，附加比例列（便于检查）
if NORMALIZE_BY_ROW:
    df_out["vegetation_prop"] = veg_prop
    df_out["sky_mean_prop"] = sky_prop
    df_out["building_m_prop"] = bld_prop
    df_out["sidewalk_m_prop"] = swk_prop

df_out["PPI"] = PPI
df_out["EBI"] = EBI
df_out["GGR"] = GGR

# ---------- 输出 ----------
df_out.to_csv(OUTPUT_CSV, index=False)
print(f"完成：已写入 {OUTPUT_CSV}，共 {len(df_out)} 行。")
