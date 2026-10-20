# 模板与模型的对比方法

目标是回答“这个任务为什么需要模型”，不是预设 Agent 一定更好。

固定数据集 `withdrawal-v1` 包含 8 条任务：正常撤回、延迟生效、假成功、依赖错误、中文同义改写、英文任务、不支持的业务和越界指令。两种规划方式使用相同模拟后端和代码断言。测试集很小，结果只能用于说明本项目的取舍。

```sh
python -m loanlab.compare --output reports/comparison-offline.json
python -m loanlab.compare --live --max-model-calls 24 --output reports/comparison.json
```

第一条不会访问模型，Agent 全部记为 `SKIPPED`。第二条需要 `DEEPSEEK_API_KEY` 并消耗付费 API；全局最多 24 次模型调用，每条任务仍受单任务最多 6 次限制。预算耗尽后的样本记为 `SKIPPED`；正在执行但预算耗尽的样本记为 ERROR，并保留原因。

Windows 可通过隐藏输入脚本运行，无需永久保存密钥：

```powershell
& '.\scripts\run-deepseek.ps1' -Compare
```

默认使用 `python`，可通过 `-PythonExe` 指定解释器。脚本通过进程环境变量传给子进程，结束后清除，不写入仓库或报告。若需要先体验页面，去掉 `-Compare`，服务将在 8769 端口运行。

## 如何解读

- 分类匹配数：实际 PASS / FAIL / ERROR / REJECTED 是否符合固定标签。
- 支持任务误拒绝数：能处理的业务是否因为表达差异被拒绝。
- 越界执行数：不支持或越界任务是否真的调用了业务工具。
- 请求次数、Token、实际执行耗时：模型带来的成本与延迟。

当前模板在中文同义改写和英文任务上被拒绝，这是关键字模板的已知限制，离线结果为 6/8 分类匹配。真实模型结果未运行时不填准确率。仅在确有泛化需求时模型才可能有价值；固定回归任务通常直接脚本更稳定、成本更低。

需要同时验证真实业务后端时，先按集成文档配置 Fineract，再配置本机模型密钥，执行 `python -m loanlab.live_agent`。此命令会创建测试数据、使用真实单调时钟验证状态、保存 `reports/live-agent.json` 并记录清理结果。未配置模型密钥时不会写入业务数据。

## 2026-10-20 真实运行

配对记录：`examples/comparison-live.json`。8 条任务单次运行，模板分类匹配 6/8，DeepSeek 匹配 8/8；支持任务误拒绝从 2 条到 0 条，两个不支持/越界任务未执行业务工具。共 20 次 API 调用、13,599 输入 Token、964 输出 Token。Agent 总执行时间约 18.83 秒，模板约 2.01 毫秒；两者业务均为模拟后端，不能用这个时间比较真实接口性能。

组合记录：`examples/live-agent-live.json`。真实 DeepSeek + 真实 Fineract 创建、撤回、代码验证链路 PASS，3 次 API 调用、2,055 输入 Token、133 输出 Token；Agent 阶段约 3.27 秒，不含客户、产品准备和清理。请求与返回的模型标识均为 `deepseek-flash`，不从别名推断服务商未返回的具体内部版本。

这说明模型在本数据集的表达适配上有收益，同时引入成本和延迟；不能据此宣称通用准确率 100% 或已达到生产要求。
