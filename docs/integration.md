# Fineract 隔离环境与真实接口回归

## 运行环境

使用 Apache 官方 Fineract 镜像与 PostgreSQL，独立 Compose 项目名为 `loanlab-fineract`。不连接现有数据库；数据库不发布主机端口，HTTP API 仅绑定本机 `127.0.0.1:18443`。这里的明文 HTTP 仅用于本机演示，不应映射到公网。

首次启动前，在仓库根目录生成本机数据库密码文件（该文件被 Git 忽略）：

```sh
python -c "from pathlib import Path; import secrets; p=Path('infra/.env'); p.exists() or p.write_text('LOANLAB_DB_PASSWORD='+secrets.token_hex(24)+'\n', encoding='utf-8')"
docker compose -f infra/compose.yml up -d
```

数据库首次初始化会创建 `fineract_tenants` 与 `fineract_default`。Fineract 首次启动需要执行数据库迁移，可用 `docker compose -f infra/compose.yml logs --tail 30 fineract` 查看进度。

## 执行真实业务用例

仅在上面的独立测试环境使用默认演示账户。PowerShell：

```powershell
$env:FINERACT_TEST_ENV = 'YES'
$env:FINERACT_BASE_URL = 'http://127.0.0.1:18443/fineract-provider/api/v1'
$env:FINERACT_USERNAME = 'mifos'
$env:FINERACT_PASSWORD = 'password'
$env:FINERACT_PRODUCT_FILE = 'examples/loan-product.json'
python -m loanlab.business --backend fineract --output reports/fineract-live.json
```

`FINERACT_PRODUCT_FILE` 用于创建本次测试专用产品，也可改用与用例金额、期限兼容的 `FINERACT_PRODUCT_ID`。`FINERACT_BUSINESS_DATE` 可显式设置 Fineract 业务日期（`yyyy-MM-dd`），不设置时使用本机当前日期。适配器遇到网络异常不会自动重试写操作，避免请求已执行但响应丢失后重复创建数据。

## 四条业务契约

| 用例 | 前置条件 | 验证 |
| --- | --- | --- |
| 待审批撤回 | 新建申请为待审批 | 请求成功且轮询观察到已撤回 |
| 已审批拒绝撤回 | 审批成功并观察到已审批 | 撤回被拒绝，原状态保持 |
| 重复撤回拒绝 | 首次撤回已生效 | 第二次被拒绝，终态保持 |
| 状态隔离 | 新建 A、B 两笔申请 | 撤回 A，B 仍待审批 |

这些契约来自所阅读的 Fineract 状态机。重复撤回被拒绝是本版本的业务契约，不应泛化为所有系统的幂等设计。负向用例同时验证响应和状态，不能只看错误码。当前未构造多角色权限矩阵，不能宣称已验证服务端越权防护。

## 数据生命周期

每次创建独立客户和带唯一标识的产品，报告记录本次资源。结束时仅对本轮创建的贷款和客户尝试删除；无法删除的终态贷款、被关联客户和产品会明确记为 `RETAINED`，网络异常记为 `UNKNOWN`，不会冒充清理成功。真实回归应在可重建的专用租户中执行，保留数据用于排查。

停止环境使用 `docker compose -f infra/compose.yml stop`，数据会保留。此文档不自动执行数据库或卷删除。

## 证据等级

`tests/test_fineract.py` 是本地 HTTP 协议契约替身；`reports/fineract-live.json` 必须由上述真实容器运行生成。二者不能混用。发布记录应注明镜像摘要、业务日期、实际用例结果和清理残留。

参考：[Apache Fineract](https://github.com/apache/fineract)，阅读基线 `1089f9bdd02030770b32660dcaef4a13df41c28e` 的 `DefaultLoanLifecycleStateMachine` 与贷款撤回集成测试。运行镜像可能与阅读基线不同，运行版本以记录的镜像摘要为准。
