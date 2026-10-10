"""Descriptive statistics shared by the dashboard and exported reports."""

import math

import numpy as np

from .evaluation import build_evaluation


GRADE_LABELS = ["I类 优质储层", "II类 良好储层", "III类 中等储层", "IV类 差储层", "V类 非有效储层"]
ANALYSIS_NOTE = (
    "统计基于本批图像的模型预测值，各样本等权；上传顺序不代表深度或空间位置。"
    "等级沿用系统预设孔渗阈值，仅作物性参考；相关性不代表因果关系，预测值需结合实测数据验证。"
)


def validate_items(items):
    if not isinstance(items, list) or not items:
        raise ValueError("没有可分析的样本，请先完成识别。")
    cleaned = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"样本 #{index} 格式不正确。")
        try:
            porosity = float(item["porosity"])
            permeability = float(item["permeability"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"样本 #{index} 缺少有效孔渗数值。") from exc
        if not math.isfinite(porosity) or not math.isfinite(permeability):
            raise ValueError(f"样本 #{index} 的预测结果不是有限数值。")
        if not 0 <= porosity <= 100 or permeability < 0:
            raise ValueError(f"样本 #{index} 的预测结果超出物理范围，请检查模型。")
        cleaned.append({
            "section_index": index,
            "filename": str(item.get("filename") or f"样本{index}"),
            "porosity": porosity,
            "permeability": permeability,
            "evaluation": build_evaluation(porosity, permeability),
        })
    return cleaned


def metric_statistics(values):
    mean = float(values.mean())
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    std = float(values.std())
    cv = std / mean if mean > 0 and len(values) > 1 else None
    outliers = []
    if len(values) >= 4:
        iqr = q3 - q1
        outliers = (np.flatnonzero((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)) + 1).tolist()
    return {
        "mean": round(mean, 4), "median": round(float(median), 4),
        "min": round(float(values.min()), 4), "max": round(float(values.max()), 4),
        "std": round(std, 4), "cv": round(cv, 4) if cv is not None else None,
        "q1": round(float(q1), 4), "q3": round(float(q3), 4),
        "outlier_indices": outliers,
    }


def summarize_results(items):
    items = validate_items(items)
    porosities = np.array([item["porosity"] for item in items], dtype=float)
    permeabilities = np.array([item["permeability"] for item in items], dtype=float)
    poro = metric_statistics(porosities)
    perm = metric_statistics(permeabilities)
    count = len(items)
    correlation = None
    if count >= 3 and np.ptp(porosities) > 1e-10 and np.ptp(permeabilities) > 1e-10:
        correlation = round(float(np.corrcoef(porosities, permeabilities)[0, 1]), 4)
    grades = [{"label": label, "count": sum(item["evaluation"]["reservoir_class"] == label for item in items)} for label in GRADE_LABELS]
    for grade in grades:
        grade["percent"] = round(grade["count"] / count * 100, 1)
    flagged = sorted(set(poro["outlier_indices"] + perm["outlier_indices"]))
    insights = [
        f"共分析 {count} 个样本。孔隙度均值 {poro['mean']:.2f}%，中位数 {poro['median']:.2f}%；"
        f"渗透率均值 {perm['mean']:.2f} mD，中位数 {perm['median']:.2f} mD。"
    ]
    if count == 1:
        insights.append("当前仅有一个样本，不评估批次离散性、孔渗相关性或统计异常值。")
    else:
        insights.append(
            f"孔隙度范围 {poro['min']:.2f}–{poro['max']:.2f}%，标准差 {poro['std']:.2f} 个百分点；"
            f"渗透率范围 {perm['min']:.2f}–{perm['max']:.2f} mD，标准差 {perm['std']:.2f} mD。"
        )
        if correlation is None:
            insights.append("有效样本不足 3 个或某项数值没有变化，暂不计算 Pearson 相关系数。")
        else:
            direction = "正相关" if correlation > 0 else "负相关" if correlation < 0 else "无线性相关"
            insights.append(f"本批孔隙度与渗透率 Pearson r = {correlation:.3f}，呈{direction}；这是批内描述性结果。")
        if count < 4:
            insights.append("样本不足 4 个，暂不进行四分位距异常值筛查。")
        elif flagged:
            labels = "、".join(f"#{index}" for index in flagged[:12])
            suffix = f"等 {len(flagged)} 个样本" if len(flagged) > 12 else ""
            insights.append(f"{labels}{suffix}超出 1.5 倍四分位距范围，建议核对图像与实测数据；该标记不代表预测错误。")
        else:
            insights.append("按 1.5 倍四分位距规则，本批未检出统计异常值。")
    populated = [grade for grade in grades if grade["count"]]
    insights.append("按系统预设阈值逐样本分级：" + "；".join(f"{grade['label']} {grade['count']} 个（{grade['percent']}%）" for grade in populated) + "。")
    summary = {
        "count": count, "metrics": {"porosity": poro, "permeability": perm},
        "correlation": correlation, "grade_distribution": grades,
        "outlier_indices": flagged, "insights": insights, "analysis_note": ANALYSIS_NOTE,
    }
    # Preserve the existing API fields used by history/report clients.
    for name, stats in (("porosity", poro), ("permeability", perm)):
        for key, source in (("avg", "mean"), ("min", "min"), ("max", "max"), ("std", "std")):
            summary[f"{key}_{name}"] = round(stats[source], 2)
    return summary
