# 各阶段输入输出契约

所有阶段通过子进程调用模块入口，模块内部不改。阶段失败不中断流程：
标 `degraded`/`unavailable` 并写原因，后续阶段能跑就继续跑。

| 阶段 | 输入 | 输出 | 失败时 |
|---|---|---|---|
| s0-discover | `--roots <目录...>` | `drawings.json`（path/size/format/project/in_archive） | `skipped`（未给 roots）或 `degraded` |
| s1a-scan | 图纸路径列表 | `scan/<图名>_detail.json` | 单张失败标 `degraded` 并记文件名，其余继续 |
| s1b-interpret | detail JSON 列表 | `<pack>/*.<pack>.json`（含 contract 三档） | `unavailable`（无 detail）或 `degraded` |
| s2-relation | 识图产物 | `relation.json` + `relation.md` | `degraded` |
| s3-aggregate | 识图产物 | `aggregate.json/.md/.csv` | `degraded` |
| s4-compare | `relation.json` | `compare-plan.json`（pairs + missing） | `degraded`：无配对时明确写「缺建筑图 N 处」 |
| s5-qty-handoff | `aggregate.json` + `relation.json` | `qty-handoff.json` | `unavailable`（无聚合结果） |
| s6-report | 全部 | `SUITE-REPORT.md` + `run-summary.json` | — |

## 状态语义

- `ok`：本阶段该做的都做了，产物存在。
- `skipped`：用户没要求（例如没给 `--roots`），不算问题。
- `degraded`：跑了但结果不完整，原因写在 detail 里（例如 5 张图里有 1 张读不出、缺建筑图无法对照）。
- `unavailable`：前置条件不满足，根本没跑（例如缺模块、缺上游产物）。
- `error`：未预期异常，栈写在 detail。

**绝不把 `degraded`/`unavailable` 写成 `ok`。** 报告里专列「降级与未执行项」。

## 契约三档

| 档位 | 含义 | 谁能进 |
|---|---|---|
| `confirmed_evidence` | 直接证据（文字标注 + 语义图层 + 坐标） | 只有识图层能判 |
| `inferred_candidate` | 推断候选，可用但需留意 | 聚合层、关系层、`#句柄` 图层的候选 |
| `review_required` | 主线不采用，需人工复核 | 缺比例/缺图层/几何冲突/重复等 |
