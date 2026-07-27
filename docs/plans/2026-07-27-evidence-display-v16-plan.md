# 证据链展示 V1.6 实施计划

## 范围

在 V1.5 证据摘要之后，清理深研报告“证据链”区域的展示噪音。

## 步骤

1. 为 `evidence_display` 契约添加失败单元测试。
2. 在快照证据校验后生成后端派生展示字段。
3. 更新前端证据链渲染，优先使用 `evidence_display`，并为历史报告提供 fallback。
4. 更新文档和变更记录。
5. 运行语法检查和后端单元测试。
6. 使用已有震安科技报告验证线上 UI。

## 回滚

回退 `backend/app/main.py`、`backend/test_main.py`、`frontend/index.html` 和本次文档更新。若后端文件已经进入运行服务，需要按 `docs/DEPLOYMENT.md` 重新构建或切回上一版容器后验证健康检查。
