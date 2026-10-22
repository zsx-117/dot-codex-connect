# Dot Codex Connect

把 MCP 客户端与自己 Mac 上的 Codex 对话连接起来：发现会话、按授权读取、发送任务、查询真实回复，并区分执行与送达回执。

**MIT 源码预览，维护者标识：zsx-117。** 核心可在自己的 Node/SQLite 服务上运行，无购买门禁、支付服务、网站统计或私有托管依赖。真实 Dot 登录及端到端尚未验收，不能称为生产开箱即用。

## 从源码开始

需要 Node 24+、Python 3.12+；无 npm/pip 包安装要求。先克隆完整源码：

```sh
git clone https://github.com/zsx-117/dot-codex-connect.git
cd dot-codex-connect
```

以下命令在仓库根目录运行：

```sh
bash skills/dot-codex-connect/scripts/setup-mac.sh --check
bash skills/dot-codex-connect/scripts/setup-mac.sh --test
python3 scripts/build-source.py --output ./connector-source.zip
```

最后一个命令生成可审计、可重复构建的 Python 源码包，不是旧预编译 App。服务启动、本机绑定和身份配置见 [自托管安装](docs/self-hosting.md)。[安装 Skill](skills/dot-codex-connect/SKILL.md) 需要整个 checkout。

## 安装为 Codex Skill

在上面克隆的仓库根目录运行。使用完整 checkout 的符号链接，保留服务器、连接器和文档的可审计路径：

```sh
skill_dir="${CODEX_HOME:-$HOME/.codex}/skills/dot-codex-connect"
mkdir -p "$(dirname "$skill_dir")"
if [ -e "$skill_dir" ] || [ -L "$skill_dir" ]; then
  echo "目标已存在，停止安装；请先检查现有 Skill。" >&2
else
  ln -s "$PWD/skills/dot-codex-connect" "$skill_dir"
fi
bash "$skill_dir/scripts/setup-mac.sh" --check
```

在新 Codex 会话里调用 `$dot-codex-connect`。不要移动/删除所链接的 checkout；安装不会替换旧 `dot-codex-install` 或启动服务。若其他 Skill 管理器仅复制 Skill 目录，需要另行克隆完整仓库，并将 `DOT_CODEX_SOURCE` 指向其绝对路径；这个 Skill 不是独立的服务端二进制包。

## 文件范围

| 目录 | 内容 |
|---|---|
| `selfhost/` | Node/SQLite 服务、静态令牌或 OAuth 资源端验证、配置与测试 |
| `service/app/{mcp,agent}`、`service/lib` | 真实 MCP、任务队列、事件、回执和单用户准入 |
| `service/connector/src` | Python 连接器、持久恢复、本机 AppServer RPC 与官方队列支持 |
| `service/drizzle` | 核心空库结构，不含支付/客户表或数据 |
| `service/tests`、`scripts` | 合成测试、确定性源码打包与构建验证 |
| `skills`、`docs` | 安装流程、架构、协议、许可、开发证据与限制 |

商业支付/统计模块、旧平台网站模板和依赖、运行状态、生产配置、旧 App 包、Git 历史均不在核心包。它们不是运行核心的必要依赖；相关本机私有备份未删除。

## OAuth 与支持范围

支持单用户静态 Bearer 模式，以及独立 OAuth 授权服务器签发的 RS256 访问令牌。OAuth 模式提供 MCP 资源发现，验证 issuer、audience、subject、client、scope、期限和签名；不提供付费身份服务或自动注册客户端。可使用自托管授权服务器，详见 [OAuth 配置与 Dot 验收](docs/oauth.md)。

源码协议与合成路由测试通过；没有验证真实 Dot 回调、客户端注册方式或登录流程。只支持单用户、Mac 主动出站和 headless 能力，不继承桌面电脑控制/审批权限。

请求受理、队列接收、目标收到、执行完成、webhook 收到和客户端 ACK 各自独立。未知发送结果先查原 requestId，不能自动补发。细节见 [架构](docs/architecture.md)、[开发记录](docs/development-history.md)、[当前验证](docs/validation.md)。

## 贡献与许可

原创代码与文档采用 [MIT](LICENSE)，公开贡献者标识是 `zsx-117`。[归属说明](THIRD_PARTY_NOTICES.md) 列明源码来源与不随包分发的组件。

欢迎贡献可复现问题、测试和文档。不要提交真实对话、密钥、设备标识或交易数据。觉得有帮助的话，欢迎点一个 Star，让更多人找到它；使用和贡献都不需要先 Star。
