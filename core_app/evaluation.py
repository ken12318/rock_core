def get_porosity_level(porosity):
    value = float(porosity)
    if value >= 20:
        return "极好", "高孔储层"
    if value >= 15:
        return "良好", "中高孔储层"
    if value >= 10:
        return "中等", "中孔储层"
    if value >= 5:
        return "较差", "低孔储层"
    return "极差", "特低孔储层"


def get_permeability_level(permeability):
    value = float(permeability)
    if value >= 200:
        return "极好", "高渗储层"
    if value >= 100:
        return "良好", "中高渗储层"
    if value >= 50:
        return "中等", "中渗储层"
    if value >= 10:
        return "较差", "低渗储层"
    return "极差", "特低渗储层"


def get_final_evaluate(porosity_level, permeability_level):
    score = {"极好": 5, "良好": 4, "中等": 3, "较差": 2, "极差": 1}
    total = score[porosity_level] + score[permeability_level]
    if total >= 9:
        return "I类 优质储层", "储集与渗流能力优秀，可作为重点开发层段。"
    if total >= 7:
        return "II类 良好储层", "孔渗条件较好，经储层改造后具备有效开发潜力。"
    if total >= 5:
        return "III类 中等储层", "物性条件一般，适合结合构造位置与含油气显示进一步评价。"
    if total >= 3:
        return "IV类 差储层", "储集空间有限、渗流能力偏弱，开发风险较高。"
    return "V类 非有效储层", "孔渗物性极差，不宜作为优先开发对象。"


def build_evaluation(porosity, permeability):
    porosity_level, porosity_desc = get_porosity_level(porosity)
    permeability_level, permeability_desc = get_permeability_level(permeability)
    reservoir_class, suggestion = get_final_evaluate(porosity_level, permeability_level)
    return {
        "porosity_level": porosity_level,
        "porosity_desc": porosity_desc,
        "permeability_level": permeability_level,
        "permeability_desc": permeability_desc,
        "reservoir_class": reservoir_class,
        "suggestion": suggestion,
    }
