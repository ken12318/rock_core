# 岩心智能识别项目

本项目面向岩心图像智能识别与储层物性评价，采用 Django 重构 Web 端，支持上传单张或多张岩心图像，利用机器学习模型预测孔隙度与渗透率，并自动生成历史记录、Excel 数据表和 Word 储层评价报告。

## 核心功能

- 岩心图像上传：支持单张检测和多张批量检测。
- 智能预测：输出孔隙度（%）与渗透率（mD）。
- 储层评价：根据孔隙度、渗透率分级生成综合储层等级和开发建议。
- 历史管理：按用户保存检测记录，支持单条删除、一键清空和 Excel 导出。
- 报告生成：自动生成 Word 格式的岩心油气储层综合评价报告。

## 图表与分析总结

识别完成后可切换样本对比、孔渗关系、数值分布、等级占比四种图表，并下载当前图表 PNG。
样本对比采用独立孔隙度/渗透率坐标轴；渗透率全部大于零时，可切换对数轴。
分析总结包含均值、中位数、范围、总体标准差、变异系数和逐样本等级占比，Word 报告使用相同统计逻辑。

- Pearson 相关系数仅在至少 3 个样本且两项数值均有变化时计算，始终基于原始数值。
- 至少 4 个样本时按 1.5 倍四分位距筛查异常值；异常仅代表需要核对，明细支持筛选。
- 单张样本不评估批次离散性或相关性。统计不能替代实测验证，也不能从上传顺序推断深度、空间分布或地层趋势。
- 等级沿用项目已有阈值，并非所有岩性的统一行业标准；均值等级与逐样本等级占比应分别解读。
- 图表库 Chart.js 4.4.8 和图标库 Lucide 0.468.0 保存在 static/core_app/vendor，本地运行不依赖 CDN。

验证统计与接口：`python manage.py test core_app`。
可选浏览器回归：设置 `ROCK_BROWSER_TEST=1`、`NODE_PATH`（含 Playwright 的 node_modules 路径）及 `ROCK_BROWSER_EXECUTABLE` 后运行同一命令。

## 项目结构

```text
.
├── manage.py               # Django 管理入口
├── rock_core_site          # Django 项目配置
├── core_app                # 识别、历史、导出等业务逻辑
├── templates               # 页面模板
├── static                  # 样式与前端脚本
└── code
    ├── machine_learning.py # 训练/实验脚本
    └── best_rock_model.pth # 当前 Web 端加载的模型权重
```

## 运行环境

建议使用 Python 3.10 或 3.11。

```bash
pip install -r requirements.txt
```

如果不使用默认数据库账号，可通过环境变量配置：

```bash
set ROCK_DB_HOST=127.0.0.1
set ROCK_DB_PORT=3306
set ROCK_DB_USER=root
set ROCK_DB_PASSWORD=root
set ROCK_DB_NAME=rock_core_db
set ROCK_SECRET_KEY=replace-with-a-random-secret
```

也可以直接提供完整连接串：

```bash
set ROCK_DATABASE_URI=mysql+pymysql://root:root@127.0.0.1:3306/rock_core_db?charset=utf8mb4
```

## 启动方式

```bash
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

启动后访问：

```text
http://127.0.0.1:8000
```

首次运行时，执行 `migrate` 会创建 Django 用户表和岩心检测历史表。

## 模型训练

训练脚本位于：

```text
code/machine_learning.py
```

默认读取：

```text
trains.xlsx
images/
```

Excel 至少需要包含以下四类列，列名可使用中文或常见英文别名：

```text
图片地址 / 图片路径 / 文件名 / image_path
岩石类别 / 岩石类型 / 岩性 / rock_type
孔隙度 (%) / 孔隙度(%) / 孔隙度 / porosity
渗透率 (mD) / 渗透率(mD) / 渗透率 / permeability
```

其中“岩石类别/岩性”不是只用于记录。训练脚本会把它编码成模型输入特征，例如：

```text
砂岩
灰岩
泥岩
白云岩
页岩
```

训练完成后，模型文件会保存这些岩性类别。网站会优先读取模型中的岩性列表作为下拉选项。岩石类型在网站中是可选项：

```text
不知道岩性：不选择岩石类型，系统自动使用通用模型，只根据图像特征预测。
清楚岩性：选择“砂岩/灰岩/泥岩/白云岩/页岩”等，系统使用对应专用模型分支，结合图像特征和岩性背景预测。
```

运行训练：

```bash
python code/machine_learning.py --data trains.xlsx --image-dir images --epochs 50 --batch-size 4
```

训练完成后会输出：

```text
code/best_rock_model.pth   # 网站直接加载的模型文件
岩心预测结果.xlsx           # 验证集真实值、预测值和误差
训练损失曲线.png            # 训练/验证损失曲线
```

新的 `.pth` 文件会保存模型权重、孔隙度标准化器、渗透率标准化器、岩性列表、列名映射、最佳轮次、验证损失和 MAE/RMSE/R2 指标。Django 推理端已经适配这种 checkpoint 格式，同时兼容旧的纯 `state_dict` 权重文件。
新训练脚本默认使用 `RockHybridModel`，它同时包含通用模型分支和岩性专用模型分支，网站会按用户选择自动切换。

## 数据库表说明

- `user`：保存用户名、密码哈希、登录 Token 和 Token 过期时间。
- `history`：保存用户检测历史、岩石类型、孔隙度、渗透率、缩略图和检测时间。

## 当前完善点

- 将原 Flask 项目重构为 Django 标准工程结构。
- 重新设计登录、注册、检测工作台和历史记录页面。
- 检测接口统一支持单张与批量图像，并返回均值、范围、标准差和综合储层评价。
- 账号体系改用 Django 内置认证，密码默认使用安全哈希保存。
- 数据库默认使用 SQLite，演示和本地运行更轻；也可通过环境变量切换 MySQL。
- 删除旧静态页面、Flask 入口、SQLAlchemy 模型和缓存文件。

## 后续建议

- 训练脚本与 Django 推理端必须保持同一套模型结构，否则重新训练出的权重可能无法被网站加载。
- 训练脚本和 Django 推理端已共用 `core_app/modeling.py` 中的模型结构与图像预处理。
- 孔隙度和渗透率标准化参数已随模型 checkpoint 一起保存，避免线上推理使用手写示例区间。
- 训练脚本已输出 MAE、RMSE、R2；正式答辩或申报时建议补充训练数据规模、岩性类别和标注来源。
- 增加图像质量检查：分辨率、模糊度、曝光异常和非岩心图片提示。
