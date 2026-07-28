# 跟踪触发器仪表盘 V2.0 实施计划

## 范围

在现有深研报告结构中新增 `tracking_dashboard`，用已有报告字段组织可执行跟踪项。

## 步骤

1. 添加失败单元测试：从 `contradiction_matrix` 和 `tracking_triggers` 生成 dashboard。
2. 添加 `TrackingDashboardItem` schema。
3. 实现 `build_tracking_dashboard(report)`。
4. 在 `_validate_report` 中补齐 `tracking_dashboard`。
5. 更新 `_schema_hint`，要求 AI 输出 dashboard。
6. 更新前端渲染“跟踪触发器仪表盘”。
7. 更新 `docs/PRD.md` 和 `docs/CHANGELOG.md`。
8. 运行语法检查、VPS 容器测试、健康检查、SSO 检查和浏览器验证。

## 回滚

回退 `backend/app/main.py`、`backend/test_main.py`、`frontend/index.html` 和本次文档更新；若已部署，按 `docs/DEPLOYMENT.md` 重建上一版容器并验证 `/yanqing/api/health`。
