# 核心矛盾证据矩阵 V1.7 设计

## 目标

把深研报告从长段落进一步升级为研究员可快速扫读的证据矩阵。用户应能在 3 分钟内看清：核心命题、支持证据、反向证据、数据缺口和后续触发器。

## 设计

- 新增 `report.contradiction_matrix`。
- 每一行包含：
  - `claim`：研究命题。
  - `supporting_evidence`：支持证据列表。
  - `opposing_evidence`：反向证据列表。
  - `data_gaps`：缺失来源或仍需核实的问题。
  - `tracking_triggers`：未来 1-3 个季度或关键公告中应跟踪的触发器。
- AI 输出提示中明确要求生成矩阵。
- 服务端在 AI 未输出矩阵或历史报告缺失时，用已有 `investment_contradiction`、`financial_diagnosis`、`policy_order_chain`、`risks_and_disconfirming_evidence` 和 `tracking_triggers` 生成保守 fallback。
- 前端在“核心矛盾”之后展示矩阵，优先帮助研究员判断证据强弱。

## 边界

- 不新增数据源，不调用 cnstock。
- 不改变 BrianHub SSO、网关、AI 配置和数据目录。
- 不输出买入、卖出、加仓、减仓等直接交易指令。
- 数据缺口必须保留 `数据不足` 或明确“待核实”。

## 验证

- 单元测试覆盖矩阵 fallback 生成。
- 单元测试覆盖 AI 输出缺失矩阵时 `_validate_report` 仍补齐矩阵。
- 前端通过历史震安科技报告验证矩阵展示。
