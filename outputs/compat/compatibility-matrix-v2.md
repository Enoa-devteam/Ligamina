# 兼容性矩阵 v2（自动生成，勿手改）

由 `python -m lab.compat_matrix_v2 build` 从已提交的证据生成；`check` 在证据变化而矩阵未重建时失败。v2 只新增第七阶段维度，`load`、`mcp_tool`、`federated_event`、`platform_delivery` 仍在 v1 矩阵中、保持不变（`base_matrix` 绑定 `outputs/compat/compatibility-matrix-v1.json` 的 SHA-256）。

| 维度 | 含义 | 证据与范围 |
| --- | --- | --- |
| `discovery` | 隔离 Worker 中的运行时命令发现 | Koishi/NoneBot：P7-04 30+30 pilot；AstrBot：冻结普查与 P7-09 inventory backfill |
| `differential` | 生成式 Native×2/Federated 逐命令比较；`verified` 只表示所有已执行命令与原生一致 | P7-04 pilot；P7-09 AstrBot campaign（含 patch run） |
| `contract` | C1–C8 通用契约；全部通过才为 `verified` | P7-04 pilot（多数检查无刺激，保持 unknown）；AstrBot 只评估 C7 |
| `stateful` | P7-07 关系：会话隔离、重启持久化 | P7-07 自身的 60 条目队列 |

取值只有 `verified`、`failed`、`skipped`、`unknown`、`untested`。任何 non-equivalent 命令使条目为 `failed`；unknown 与 nondeterministic 保持 `unknown`，不改写为通过。各维度队列不同，见每条结论的 `scope`。本矩阵是证据索引，不是支持名单，也不表示插件业务正确。

## 按生态与维度的计数

| 生态 | 目录条目 | 维度 | 计数（平台:取值） |
| --- | --- | --- | --- |
| astrbot | 3271 | `discovery` | linux:skipped 253, linux:verified 3012, untested 6 |
| astrbot | 3271 | `differential` | linux:failed 284, linux:skipped 779, linux:unknown 778, linux:verified 1171, untested 259 |
| astrbot | 3271 | `contract` | linux:unknown 2233, untested 1038 |
| astrbot | 3271 | `stateful` | untested 3271 |
| koishi | 4747 | `discovery` | linux:verified 30, untested 4717 |
| koishi | 4747 | `differential` | linux:failed 6, linux:skipped 13, linux:unknown 2, linux:verified 9, untested 4717 |
| koishi | 4747 | `contract` | linux:unknown 30, untested 4717 |
| koishi | 4747 | `stateful` | linux:unknown 30, untested 4717 |
| nonebot | 943 | `discovery` | linux:failed 4, linux:verified 26, untested 913 |
| nonebot | 943 | `differential` | linux:failed 2, linux:skipped 15, linux:unknown 7, linux:verified 6, untested 913 |
| nonebot | 943 | `contract` | linux:unknown 30, untested 913 |
| nonebot | 943 | `stateful` | linux:skipped 1, linux:unknown 29, untested 913 |

## 覆盖度

| 生态 | 已执行命令 | equivalent | non_equivalent | nondeterministic | unknown | 契约检查（检查:状态） |
| --- | --- | --- | --- | --- | --- | --- |
| astrbot | 14937 | 10082 | 653 | 3043 | 1159 | C7:passed 13792, C7:unknown 1145 |
| koishi | 90 | 56 | 31 | 0 | 3 | C1:passed 16, C1:unknown 14, C2:unknown 30, C3:unknown 30, C4:unknown 30, C5:unknown 30, C6:unknown 30, C7:unknown 30, C8:unknown 30 |
| nonebot | 87 | 65 | 3 | 2 | 17 | C1:passed 14, C1:unknown 16, C2:unknown 30, C3:unknown 30, C4:unknown 30, C5:unknown 30, C6:unknown 30, C7:unknown 30, C8:unknown 30 |
