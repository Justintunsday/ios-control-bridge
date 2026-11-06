# 连接 iOSRemoteBridge

先确认已安装的设备插件、现有私有 `client-config.json` 和 Python 环境。
使用配置中的证书固定和配对，不重新生成凭据，也不把 token 放进参数或日志。
这是 TLS / IRB1 协议，普通 VNC 客户端不能替代。

包内后端位于 `/var/jb/usr/lib/iosremotebridge`，Python 3.9+ 无依赖入口：

```sh
cd /var/jb/usr/lib/iosremotebridge
python3 -S -m automation.mcp_stdio --config /absolute/private/client-config.json --control
```

这是一条 MCP stdio 启动命令，交给 MCP 客户端管理。查看模式省略 `--control`。
初始化和列举工具不连接手机，首次设备调用才连接。SDK 入口是
`automation.mcp_server`，其额外 Python 依赖见上游说明。

已有 Control API 和 OpenCode 时，使用包内的 `opencode-ios-bridge setup`
和 `doctor` 配置与检查。先用 `opencode debug paths` / `debug config` 找到
实际服务端配置，root 与 mobile 可能使用不同用户目录；保留 provider、其他
MCP 服务器和 JSONC 注释。预览后通过 `--apply` 保存，修改已有服务配置后
再按该服务的正常方式重载。配对端点以真实配置为准，不能假定回环地址监听。

新的 stdlib 和 SDK 入口共享 14 个工具及其参数验证；实际清单优先。
MCP connected 或 doctor 成功只验证适配器发现，不代表手机解锁、模型收到
图片或触控生效。实际调用设备信息、查看图片，执行授权动作后再看新图片。

其他客户端可发现这个完整技能目录，或在支持的技能路径设置中引用它。
不要同时发现同名技能的多份副本。OpenCode v2.2.5 支持在配置的 `skills`
数组中加入 `/var/jb/usr/lib/iosremotebridge/skills`；按实际版本核对配置格式。

上游：[iOSRemoteBridge](https://github.com/Justintunsday/iOSRemoteBridge)，
[自动化接口](https://github.com/Justintunsday/iOSRemoteBridge/blob/main/docs/AUTOMATION.md)。
