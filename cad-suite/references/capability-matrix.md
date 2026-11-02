# 七技能能力 × 融合阶段对应表

| 技能 | 版本 | 核心能力 | 在融合流程里的位置 | 不做什么 |
|---|---|---|---|---|
| cad-file-reader | 0.38.6 | DWG/DXF/DWT/PDF 本地解析；图层/文字/块/图框/几何提取；16 类专业识图 pack（结构、建筑、总图场地、安装、电气、钢结构、市政、给排水暖通、精装修、幕墙、人防、预制装配、园林景观等）；统一候选契约与置信分层；大图缓存、局部解析、图纸对比 | s0 发现、s1 识图、s2 关系、s3 聚合 | 不算量；不出吨位/体积/面积/造价 |
| tujian-suanliang | 0.9.30 | 结构图出混凝土方量与钢筋估算带；梁板柱墙/楼梯/洞口/预制底板/结构模型；标号分账、扣减台账、后浇带分账；计划口径 ±5~10% | s5 派发目标（土建） | 不替代翻样/下料/结算 |
| zhuangshi-suanliang | 0.9.29 | 房间装修表/做法表/节点；做法映射、洞口扣减、损耗、材料台账与清单量；装饰概算与物资计划 | s5 派发目标（装饰） | 不做结构算量 |
| anzhuang-suanliang | 0.4.28 | 回路规格分档管线；电线芯线与预留展开；电缆/桥架/给排水/喷淋/支吊架/设备数量；概算底稿与物资计划双口径 | s5 派发目标（安装） | 不替代翻样/下料/结算；不出金额 |
| yuanlin-suanliang | 0.4.32 | 中英文图例苗木分类统计；苗木表设计基线；闭合区域铺装面积；DXF 块内铺装展开；置信分层 P0–P3 | s5 派发目标（园林） | 不替代设计复核/放线/竣工计量 |
| lis-skill-bus | 0.1.5 | 本地 MCP server 安装壳：把 5 个 CAD 技能的项目状态与识图契约接在一起，同一张图只解析一次、各技能共享复用 | 跨阶段状态复用（可选） | 不解析图纸、不算量 |
| cad-clash-check | 0.3.0 | 消费识图产物，构件三分类、轴格定位、2D 空间候选、属性冲突、预留通道与穿墙语义；输出 JSON/MD/施工计划模板 | s4 跨专业碰撞校对与批量 `--with-clash` | 2D 倾向提示，非 BIM 碰撞检测；不算量 |

## 阶段与模块入口的对应

| 阶段 | 实际执行者（modules/ 内路径） | 产出 |
|---|---|---|
| s0 发现 | `cad-file-reader/scripts/drawing_source.py` | `drawings.json` |
| s1a 解图 | `cad-file-reader/scripts/cad_scan.py` | `scan/<图名>_detail.json` |
| s1b 识图 | `cad-file-reader/scripts/cad_structural_geometry.py` 等 pack 脚本 | `structural/*.structural.json` |
| s2 关系 | `cad-file-reader/scripts/drawing_relation.py`（专业判定 / 图种 / 楼栋 / 配对） | `relation.json/.md` |
| s3 聚合 | `cad-file-reader/scripts/project_aggregate.py` | `aggregate.json/.md/.csv` |
| s4 对照 | 读 s2 的配对建议（本层不重算；按楼层/楼栋/大样三种范围） | `compare-plan.json` |
| s5a 图框 | `cad-file-reader/scripts/qty_prepare.py`（定图框标题与板厚） | `qty-prepare.json` |
| s5 算量 | 子进程调 `modules/<skill>/scripts/...`（真跑，不是只开单） | `qty-handoff.json` + `qty/` |
| s6 出表 | `scripts/suite_run.py` 汇总 | `SUITE-REPORT.md` |

## 为什么算量不并进来

四个算量技能各自是**多步流水线**（梁归并冲突、跨闭合、实例去重、标号分账、扣减台账、损耗、块内展开……），
每步都有独立单测网（土建 325 项、装饰 28 项、园林 26 项、安装 64 项断言）。

把它们复制进融合层会立刻产生两份会分叉的实现——这正是要避免的。
融合层的价值是**把「要算什么、哪些图、哪些楼层、哪些构件规格」一次说清楚**，
再交给专业技能按自己的流水线算。
