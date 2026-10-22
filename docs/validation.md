# 源码预览验收

日期：2026-10-22。macOS、Node 24.19.0、Python 3.12.14。数据为合成 fixture，不使用真实客户/交易/聊天；OAuth 测试签名密钥仅在进程内存中存在。

| 检查 | 当前结果 | 范围 |
|---|---|---|
| `(cd selfhost && node --test test.mjs oauth.test.mjs oauth-route.test.mjs)` | 8 通过 | 实际 MCP/agent 路由、稳定请求/单调同步、静态认证隔离、OAuth 元数据/签名/claims/故障拒绝 |
| `python3 scripts/test_python.py` | 48 通过 | 真正连接器源码的恢复锁、writer/队列/steer、探测、补传等合成回归 |
| `(cd service && node tests/cloud.mjs)` | 6 组 PASS | 去重、owner 隔离、事务、事件、订阅、回执/ACK |
| `(cd service && node --test tests/task-state.mjs tests/communication.mjs)` | 9 通过 | 等待时限、取消、回复状态与通信边界 |
| `python3 scripts/test_source_build.py` | 通过 | 两次源码归档 hash 一致；独立解压自检与子进程启动；未读取账号 |
| Skill 格式与 setup helper | 通过 | 格式、完整源码入口及离线工作流 |
| `(cd selfhost && node --test http.test.mjs)` | 1 通过 | 授权后重试一次；临时 127.0.0.1、内存 SQLite、合成凭据；已关闭 |

本轮核心已无商业模块，第一轮 18/46 项权益/商业测试不再算当前核心测试数；它们的源码与旧结果仅在本机私有备份。第一轮对 device/connector 的重复 47 项也不合并成额外场景。

OAuth 合成测试的 JWKS 获取完全 mocked；静态核心闭环测试禁止 fetch。Python runner 使用临时源码与状态，拦截网络和真实 Codex 启动。不是恶意代码 OS 沙箱审计。

HTTP 测试首次因沙箱 EPERM 未启动，后来经用户明确授权和受支持审批重试一次通过。此结果仅覆盖本机合成 HTTP 请求；真实用户凭据、OAuth 登录、HTTPS、Mac 账户与业务会话未使用。

仓库 CI 在 macOS/Linux 上复跑核心/OAuth、Python、状态/队列、源码构建和临时 loopback HTTP 测试。以对应 commit 的 GitHub Actions 结果为准；CI 不代表真实 Dot 链路验收。

仍未验证：实际 HTTPS 代理、真实授权服务器导入/登录、Dot 客户端注册和 OAuth 回调、真实 Mac 账户绑定/选定会话收发、真实 webhook/ACK、断网重启全链路、新版 CLI 兼容、签名/公证 App。明确步骤与最小权限见 [OAuth 与 Dot](oauth.md)。原收费 App 不作为本次源码构建证据。
