# 本地验证记录

日期：2026-10-20。运行环境：Windows / Python 3.12.6。

- `python -m unittest discover -s tests -v`：27 项通过。模型协议与工具调度使用测试替身，没有请求真实模型。
- `python -m loanlab.evaluate`：5 个固定场景的实际分类与预期匹配。数据来自内存模拟，不是模型泛化测试。
- 浏览器：正常撤回显示 PASS；假成功场景显示 FAIL、HTTP 200 和期限内仍待审批的证据，历史报告可读取。截图见 `demo.png`。
- Python 源码编译检查通过；暂存文件空白检查通过。

尚未验证：真实 DeepSeek API 连通性、真实 Fineract 环境、GitHub Actions 云端运行。后续接通后在此追加可复现记录，不将配置存在当作连接成功。
