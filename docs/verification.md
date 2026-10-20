# 本地验证记录

日期：2026-10-20。运行环境：Windows / Python 3.12.6。

- `python -m unittest discover -s tests -v`：27 项通过。模型协议与工具调度使用测试替身，没有请求真实模型。
- `python -m loanlab.evaluate`：5 个固定场景的实际分类与预期匹配。数据来自内存模拟，不是模型泛化测试。
- 浏览器：正常撤回显示 PASS；假成功场景显示 FAIL、HTTP 200 和期限内仍待审批的证据，历史报告可读取。截图见 `demo.png`。
- Python 源码编译检查通过；暂存文件空白检查通过。

尚未验证：真实 DeepSeek API 连通性、真实 Fineract 环境、GitHub Actions 云端运行。后续接通后在此追加可复现记录，不将配置存在当作连接成功。

## 后续补齐记录（同日）

- 初始公开版本 GitHub Actions Python 3.12 / 3.13 检查已通过。
- 扩展版 42 项本地自动化检查通过，包括 HTTP 适配契约、业务错误放行故障变体、评测预算与离线 SKIPPED 行为。
- 真实 Fineract 官方镜像 + PostgreSQL 已运行；四条业务回归全部通过，记录于 `examples/fineract-live.json`。本次未调用真实模型。
- 实测撤回终态和已审批贷款不能直接删除，清理状态为 PARTIAL；残留资源逐条列出。
- 8 条任务离线评测中模板匹配 6 条，同义改写和英文任务被拒绝；Agent 全部 SKIPPED，无真实模型结果。

## 模型实测追加（同日）

- 真实 DeepSeek 配对运行已完成：8 条固定模拟任务，模板 6/8、模型 8/8，20 次模型调用；见 `examples/comparison-live.json`。
- 真实模型 + Fineract 完整工具链路已通过：3 次模型调用，由代码验证最终撤回状态；见 `examples/live-agent-live.json`。
- 发布证据只包含合成业务数据、工具轨迹和 Token 统计，不包含 API 密钥、Authorization 或隐藏思考内容。
