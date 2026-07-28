# 跟踪触发器仪表盘 V2.0 设计

## 目标

把“跟踪触发器”从普通文本列表升级为研究员可执行的观察仪表盘。用户应能快速知道：下一期看什么、为什么看、当前状态是什么、什么情况会验证或推翻当前研究命题。

## 设计

- 新增 `report.tracking_dashboard`。
- 每个跟踪项包含：
  - `trigger`：需要观察的触发器。
  - `status`：`watch`、`data_insufficient`、`confirmed`、`invalidated` 之一。
  - `why`：该触发器与核心矛盾的关系。
  - `evidence`：当前已有证据或结构化事实。
  - `next_check`：下一步应检查的财报、公告、订单或字段。
  - `invalidate_if`：什么情况会推翻当前判断。
- AI 新报告可原生输出 `tracking_dashboard`。
- 服务端为历史报告和缺失字段的 AI 输出生成 fallback：
  - 优先使用 `contradiction_matrix[].tracking_triggers`。
  - 其次使用 `report.tracking_triggers`。
  - 证据来自矩阵支持/反向证据和证据展示摘要。
  - 缺少证据时明确标记 `数据不足`。
- 前端在“核心矛盾证据矩阵”之后展示跟踪仪表盘。
- 历史报告缺少 `tracking_dashboard` 时，前端可从 `tracking_triggers` 和 `contradiction_matrix` 即时生成展示 fallback。

## 边界

- 不新增外部数据源。
- 不调用 cnstock，不读取 cnstock 数据、缓存、Cookie、数据库或报告资产。
- 不修改 BrianHub SSO、网关、AI 配置、数据目录或密钥边界。
- 不输出买入、卖出、加仓、减仓等直接交易指令。

## 验证

- 单元测试覆盖 dashboard fallback。
- `_validate_report` 缺失 `tracking_dashboard` 时自动补齐。
- 后端完整单元测试通过。
- 浏览器验证线上报告页出现“跟踪触发器仪表盘”区域。
