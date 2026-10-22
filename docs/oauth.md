# OAuth 资源端与 Dot 的兼容性边界

## 已实现与验证

服务新增 `/.well-known/oauth-protected-resource/mcp`（根路径也支持）以及 401 `WWW-Authenticate: Bearer resource_metadata=...`。元数据指向操作者配置的 issuer。资源端固定 RS256，验证签名、受众、issuer、操作者 sub、授权客户端、scope、时间范围，并拒绝 ID token、嵌入 JWK/外部 key URL 和静态令牌回退。授权服务器负责登录、授权码和 PKCE；本服务不自行发令牌。依据 [MCP 授权规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)。

已用内存 RSA 密钥、合成 JWT 和 mocked JWKS 跑过正反向验证，并经过实际 MCP 路由验证准入。未做真实 Dot 浏览器登录或 OAuth 客户端注册，不宣称完整 OAuth/MCP 认证兼容性验收。

## 可自托管路线

可使用自己的 Keycloak 或其他符合下面配置的授权服务器。Keycloak 的 OIDC discovery 和公开证书端点由其 [官方文档](https://www.keycloak.org/securing-apps/oidc-layers) 定义。此文档是部署建议，不是已配置实例。

1. 在独立测试 realm/issuer 配置 Authorization Code + PKCE S256。关闭密码 grant 和 implicit flow；不使用生产 realm。
2. 用 Dot 当前界面实际给出的回调地址做精确 allowlist，禁止猜测 URL、通配符或自动动态注册。本轮不知道 Dot 的当前回调地址和客户端注册能力。
3. 预配置一个专用客户端/授权范围 `codex:bridge`，访问令牌 audience 精确包含自己的 `https://HOST/mcp`，操作者只允许一个 sub。配置专用 audience mapper，签发 RS256 access token；令牌含 `azp` 或 `client_id`、`iat`、`exp`、`scope`。接受 RFC 风格 `typ=at+jwt`，或 Keycloak 风格 header `JWT` + payload `Bearer`。
4. 将 issuer/JWKS URI/resource/client ID/operator sub 写入 `.env.oauth.example` 对应字段。JWKS 必须与 issuer 同源；access token 最大生命周期一小时，建议在授权服务器设为几分钟。不要设置 `DOT_MCP_TOKEN`。
5. 资源端只按公开 JWKS 验证，不传递 token 给其他业务服务。JWKS 最多缓存五分钟，未知 kid 刷新最多每分钟一次；轮换可能短暂拒绝新 key。没有实时 introspection/revocation，已签发 token 的撤销最迟在其过期时生效；请用短期 access token。

可审阅的配置样例为 `selfhost/keycloak-realm.example.json`：realm/client 默认 disabled，无用户、无密码、无客户端 secret，回调和 audience 使用 `.invalid`。没有导入或注册；实际 Keycloak 版本导入与 Dot 公共客户端/预注册支持均未测。必须填入客户端真实回调并审查后才能在独立测试实例启用；不要用样例猜测回调。

## 必须由用户决定/完成的最小动作

| 动作 | 精确用途与最小权限 | 本轮状态 |
|---|---|---|
| 允许隔离 loopback 监听 | 临时本机端口，只使用合成数据，不暴露公网、不创建凭据 | 已获授权，一次重试通过；临时监听已关闭 |
| 提供自己控制的测试 HTTPS 服务与 issuer | 独立测试域名、证书与授权服务器；不修改现有线上部署 | 未提供/未部署 |
| 注册测试 OAuth 客户端 | 精确 Dot callback、仅 `codex:bridge`、PKCE；不默认申请额外 scope | 明确不在本轮授权内，未执行 |
| 用户亲自登录并同意 | 在自有 issuer/Dot 页面批准上述范围 | 未执行 |
| 提供已有测试设备凭据，或另行明确授权创建 | 仅该测试 connector 到测试服务；当前不生成持久凭据 | 未提供/未生成 |
| 批准在新状态目录绑定自己的 Mac | 公共 AppServer account/read；不读取其他会话或改生产桥接 | 未执行 |
| 指定一个可丢弃测试会话及一次发送 | 只读该会话、发送一条合成标记、查询同 requestId | 未执行 |
| 明确允许该测试结果的 webhook/ACK | 只对实际 Dot 测试接收端验证；不得猜测或扩大收件人 | 未执行 |

这些动作不应被“离线测试通过”替代。若 Dot 不支持预注册客户端参数，需核对其支持的注册机制与自有授权服务器能力；不得冒用旧私有平台 OAuth，也不得为兼容自动开放无审查动态注册。

## 仍有限制

目前仅单用户资源端，未实施多租户、OAuth 授权服务器、SSE 推送或完整 MCP conformance suite；错误范围挑战统一返回 401，并没有实现逐工具 step-up。events 是原产品扩展，真实 Dot 支持情况仍待验证。服务器 POST 拒绝 Origin，当前面向服务端 MCP 客户端。自托管这条路不需要购买原服务，但需要使用者自己控制身份系统和部署环境。
