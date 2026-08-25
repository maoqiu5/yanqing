# Yanqing 研擎交接说明

> 更新时间：2026-08-25
> 接手原则：VPS `/root/apps/yanqing` 为生产事实；本地 `D:\codex\yanqing` 为开发源码。

## 1. 项目一句话

独立个股研究工作台：用户输入股票名称或代码，系统采集公开资料并让 AI 分析基本面、关键矛盾、证据、风险、研究问题和跟踪触发点。

## 2. 当前状态

- 线上：`https://brianhub.net/yanqing`
- VPS 目录：`/root/apps/yanqing`
- 本地目录：`D:\codex\yanqing`
- 技术栈：Python / FastAPI + 前端
- VPS 无 `.git`
- 独立边界：不调用 cnstock API、不读 cnstock 数据、不复用 cnstock 登录
- 本地已同步 VPS 最新源码：✅（2026-08-25）
- 本地测试：`45 passed, 2 skipped, 1 failed`（失败为 Windows 缺少 `os.killpg`，VPS Linux 应正常）

## 3. 核心能力

- 自动采集公告、年报、半年报、季报
- 证据元数据和摘录
- `evidence_digest` 证据摘要
- `contradiction_matrix` 矛盾矩阵
- `tracking_dashboard` 跟踪看板
- `financial_traceability` 财务字段溯源
- 研究判断、PDF 导出
- 门户 SSO 保护

## 4. 关键路径

- VPS 数据目录：`/root/apps/yanqing/data`
- AI 配置：通过门户 `/internal/ai-config`
- 环境变量：`TUSHARE_TOKEN`、`PORTAL_INTERNAL_TOKEN`

## 5. 部署

```bash
cd /root/apps/yanqing
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

验证：

```bash
curl -fsS https://brianhub.net/yanqing/ >/dev/null
```

## 6. 安全

- 不读取/输出 `PORTAL_INTERNAL_TOKEN`、TUSHARE Token、数据库
- 不把 cnstock 和 yanqing 数据混用
- 不自动交易

## 7. 新对话接续

```text
这是 yanqing 项目对话。
请先读 D:\codex\HANDOVER_INDEX.md 和 D:\codex\yanqing\docs\HANDOVER.md，
再查看 VPS /root/apps/yanqing 状态，然后开始工作。
```
