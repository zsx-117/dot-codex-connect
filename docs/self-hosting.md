# 自托管安装与源码构建

除明确进入子目录的命令外，下列代码块均从仓库根目录执行。子目录命令使用子 shell，不改变后续命令的工作目录。安装 Skill 见 [README](../README.md#安装为-codex-skill)。

## 离线检查

要求 Node 24+、Python 3.12+，使用内置模块，不运行 npm/pip 安装脚本。

```sh
bash skills/dot-codex-connect/scripts/setup-mac.sh --check
bash skills/dot-codex-connect/scripts/setup-mac.sh --test
```

解释器不在 PATH 时，设置 `DOT_NODE_BIN` / `DOT_PYTHON_BIN`。测试使用合成身份；OAuth 测试密钥只在内存中存在，不存盘、不注册真实账户。HTTP 监听测试另行运行 `(cd selfhost && node --test http.test.mjs)`，它只监听临时 loopback 端口；初次受沙箱 EPERM 阻塞，获得用户授权后的一次重试通过，监听已关闭。

## 本机连接器源码构建

```sh
python3 scripts/build-source.py --output ./connector-source.zip
python3 scripts/test_source_build.py
```

归档包含 11 个 Python 模块、MIT 许可、运行说明和文件哈希，时间/排序/模式固定。同输入构建两次哈希一致；独立解压后子进程自检通过。它不是 macOS App、不含二进制、签名或公证。用标准 Python 运行，无 Gatekeeper/quarantine 修改。

## 服务：静态或 OAuth 模式

静态模式复制 `selfhost/.env.example`；OAuth 模式复制 `.env.oauth.example`。配置文件不提交 Git；样例无可用凭据。由部署者提供自己管理的设备凭据，静态模式再提供不同的 MCP 凭据。OAuth 模式禁止静态令牌后门。当前准备没有创建任何真实持久凭据。

```sh
(cd selfhost && node --env-file=.env server.mjs)
```

服务构建本地 `.generated/`，初始化自己的 SQLite，绑定 `127.0.0.1:8787`。全新状态目录、运行用户独占，umask 077；不能指向现有付费服务数据库。一个进程只支持一个 operator 和数据库。源码没有支付/权益服务调用，也没有客户/交易表。

部署者需用自己维护的 HTTPS 代理暴露 `/mcp`、`/agent`；OAuth 模式还暴露 `/.well-known/oauth-protected-resource/mcp`。代理保留认证头、限制流量，禁止记录正文与凭据。不接受直接浏览器 Origin POST；浏览器直连不在验证范围。当前任务没有创建域名、代理、证书或部署。

OAuth 登录、精确配置和必须由用户操作的步骤见 [OAuth 与 Dot](oauth.md)。静态 Bearer 不能冒称 OAuth。

## Mac 显式绑定与前台运行

Mac 已有可用 Codex CLI 和用户自己的登录环境。设置 `DOT_CONNECT_SERVICE` 为自己的 HTTPS origin，`DOT_DEVICE_TOKEN` 为服务设备凭据，`DOT_CONNECT_HOME` 为**全新绝对路径**。

```sh
python3 selfhost/configure_mac.py --home "$DOT_CONNECT_HOME" --approve-account-binding
python3 service/connector/src/connector.py run --home "$DOT_CONNECT_HOME"
```

绑定命令经公共 AppServer 读取当前账户身份，确认设备心跳后保存 fingerprint 与配置；不读取账号文件或聊天，不发送任务，不创建密钥。遇到已有状态拒绝覆盖。第二个命令前台运行，不安装 launchd。源码 CLI 已删除旧购买配对/商业安装入口。系统 CA 继续验证 TLS，证书错误应修复 CA/代理配置，不能关闭验证。

账户绑定、真实设备心跳和请求收发本次未执行。若部分绑定失败，保留私有状态并核对，不能自动换 key 或覆盖目录。

## 逐层验收与停用

先 initialize/tools/list，再检查访问状态/设备 heartbeat。获得对指定可丢弃测试会话的授权后才 list/read/send；每次使用稳定 requestId。检查目标 turn 和实际回复，再单独验证 webhook 接收与应用 ACK。停止前台进程即可停用，状态保留；删除状态或撤销凭据须另行明确操作。

Webhook 目的地使用系统 DNS，并固定公开 IP 验证 TLS；源码版移除了内置外部 DNS fallback。若 VPN 返回 Fake-IP/私有地址，发送会拒绝，需操作者修复自己的 DNS 配置；本任务不改变 VPN 或系统 DNS。
