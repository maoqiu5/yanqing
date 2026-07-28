# 核心矛盾证据矩阵 V1.7 实施计划

## 范围

在现有自动深研报告中增加核心矛盾证据矩阵，不扩展新数据源。

## 步骤

1. 添加 `ContradictionMatrixRow` schema 和矩阵 fallback 测试。
2. 实现 `build_contradiction_matrix(report)`，从现有报告字段保守生成矩阵。
3. 在 `_validate_report` 后补齐 `contradiction_matrix`。
4. 更新 `_schema_hint`，要求 AI 原生输出矩阵。
5. 更新前端，在核心矛盾之后展示矩阵。
6. 更新 PRD 和 CHANGELOG。
7. 运行语法检查、容器单元测试、线上健康检查和浏览器验证。

## 回滚

回退 `backend/app/main.py`、`backend/test_main.py`、`frontend/index.html` 和本次文档更新；若已上线，按 `docs/DEPLOYMENT.md` 重建上一版容器并验证 `/yanqing/api/health`。
