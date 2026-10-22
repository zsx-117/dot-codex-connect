# 许可与归属

根目录 MIT 版权署名为 **zsx-117 and contributors**，按项目维护者授权使用公开账号标识，不添加真实姓名或邮箱。该许可覆盖本包原创连接核心、适配代码、合成测试和文档，不重新授权第三方产品、运行时或旧 App。

## 来源核对与范围收敛

连接核心来源固定于服务 Git 提交 `e5fc9f80df007c703c014638f0dd08af2ebd22ec`。Git 记录显示 MCP/agent/bridge 于 `edc0d4c`（2026-10-06）进入项目，事件库于 `0c0d1594`（2026-10-07）加入，发行连接器源码于 `551e2b77`（2026-10-10）加入。可核对版本来源；Git 记录本身不是独立版权链证明。

原项目同时含 Sites/React UI 模板、构建插件及大量前端依赖。找到的 `sites-vite-plugin.LICENSE` 是 OpenAI MIT，但不能据它推断所有模板许可。第二版核心包已移除整个网站模板、构建插件、前端包锁和依赖；原许可与文件留在本机私有备份。它们不被本源码构建或运行加载，因此不再构成核心包模板归属待核项。

没有复制 `Fanch-hui/codex-bridge` 源码；第三方评估不被作为本项目许可证或验收依据。商业结账/统计参考也未随核心包分发。

## 运行时与可选外部系统

本包使用 Node 内置 HTTP/crypto/SQLite 与 Python 标准库；不捆绑 Node、Python、SQLite、Codex CLI、CA 证书包、npm/pip 包或签名 App。使用这些系统时，其原许可与商标权不受项目 MIT 替代。

OAuth 授权服务器可由部署者选择并自行托管；文档提到 Keycloak 仅是配置路线，未复制/分发其程序或许可证文本。授权服务器、HTTPS 代理与 Codex 自有许可仍各自适用。

旧公开安装器的限定许可与旧收费 App 不能作为当前源码 MIT 版的编译对应证据；当前交付是可审计源码运行路径，非旧 App 重贴许可。

MIT 条文依据 [OSI MIT License](https://opensource.org/license/mit)。Star 从来不是许可条件。
