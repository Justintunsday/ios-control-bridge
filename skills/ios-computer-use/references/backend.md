# iOSRemoteBridge 后端

上游：[iOSRemoteBridge](https://github.com/Justintunsday/iOSRemoteBridge)，自动化说明见其 [AUTOMATION.md](https://github.com/Justintunsday/iOSRemoteBridge/blob/main/docs/AUTOMATION.md)。它使用带证书固定的 TLS / IRB1 与 H.264，而非标准 RFB/VNC；不能用普通 VNC 客户端替换认证协议。

2026-11-05 接入使用的 Python 客户端提交为 `24e7a212eb3f4cd8602e884bdba02a54fa16a092`，可选依赖为上游 `automation/requirements-mcp.txt` 中的 `mcp==2.3.0`。真机是已有安装，服务端源码提交未知；不要把客户端提交当成设备二进制版本。测试结论见 iOS Control Bridge 仓库 `docs/iosremote-computer-use.md`。

## 主机准备

需要已经安装并正常运行的设备插件、已有 `client-config.json`、对应的 Python 环境和后端源码目录。复用现有配对，token 仅由客户端从私有文件读取；命令参数、提示词、公共配置和日志中只放文件路径。不要为一次接入重新生成配对或重新安装手机插件。

在独立环境安装上游可选依赖后，从任意工作目录运行 iOS Control Bridge 的启动器：

```text
PYTHON_ABSOLUTE_PATH ICB_ROOT/tools/run_iosremote_mcp.py --bridge-root IRB_ROOT --config PRIVATE_CLIENT_CONFIG --control
```

上述大写项均为占位符，三个路径参数应使用真实绝对路径。启动器只转交给上游 MCP stdio 服务；不访问 iosctl 注册表，不安装设备软件。查看模式可省略 `--control`。适配器初始化和列举工具不要求手机在线，首次 `get_device_info` / `get_screen_frame` 才连接。

## 两种客户端

Codex 的 `config.toml` 增加独立条目，保留现有设置：

```toml
[mcp_servers.iosremote]
command = "PYTHON_ABSOLUTE_PATH"
args = ["ICB_ROOT/tools/run_iosremote_mcp.py", "--bridge-root", "IRB_ROOT", "--config", "PRIVATE_CLIENT_CONFIG", "--control"]
tool_timeout_sec = 80
```

OpenCode 的 `opencode.json` / `opencode.jsonc` 在现有 `mcp` 中加入：

```json
{
  "mcp": {
    "iosremote": {
      "type": "local",
      "command": ["PYTHON_ABSOLUTE_PATH", "ICB_ROOT/tools/run_iosremote_mcp.py", "--bridge-root", "IRB_ROOT", "--config", "PRIVATE_CLIENT_CONFIG", "--control"],
      "enabled": true,
      "timeout": 80000
    }
  }
}
```

这两个片段是合并示例，不能覆盖整个已有配置。先用实际 Python 进程验证 MCP 初始化与工具列表，再重载相应客户端。仅写配置或 MCP SDK 收到图片，不证明模型已经看见图片；模型侧还需实际打开一帧并描述所见。

OpenCode 2.0.26 实测能读取上述兼容配置，并把它规范化为 `mcp.servers`、`disabled:false` 及 catalog/execution 超时。已有后台服务修改文件后需 `opencode reload`；再用 `opencode mcp list` 确认 `iosremote connected`。目录已连接不等于配对设备已连接。

共享技能可放入 `~/.agents/skills/ios-computer-use`；避免在多个发现目录安装同名副本。[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)、[Codex skills](https://learn.chatgpt.com/docs/build-skills)、[OpenCode MCP](https://opencode.ai/docs/mcp-servers/)、[OpenCode skills](https://opencode.ai/docs/skills/)。

不要让两端同时调用设备工具。上游设备端一次只允许一个会话，持有者结束任务应 `disconnect()`。若锁定、超时或远程会话被占用，报告实际错误，继续不依赖设备的工作，不禁用手机自动锁定或改写锁屏检查。

## 手机上的 Python 3.9

当前越狱设备的 Python 为 3.9.9，上游 MCP 2.3.0 要求 Python 3.10+。手机可在同一个启动命令中增加 `--stdlib`；更新后的启动器会转交上游 `automation/mcp_stdio.py`，由上游共享工具清单和参数校验。正式设备包入口是 `python3 -B ICB_ROOT/bin/iosctl iosremote --bridge-root IRB_ROOT --config PRIVATE_CLIENT_CONFIG --stdlib`，原 `tools/run_iosremote_mcp.py` 保留兼容。它继续使用上游证书固定和配对，不另开 HTTP 端口，不重装设备插件。旧后端仅在源码目录保留十工具兼容回退，并向 stderr 提示升级。

新的原生 stdlib 入口与 SDK 入口提供相同的 14 个工具：原有十项加性能信息、双击、长按和实验性 App 启动。工具已暴露不等于动作已通过真机验证。`insert_text` 需要同时更新原生插件，旧版插件不支持；以 `input_diagnostics.literal_text_ready` 判断已安装后端是否就绪。只读会话先拒绝输入，数值/坐标/时长及文本边界由主机与设备分别校验；错误不自动重发。

OpenCode 可用 `iosctl opencode setup` 生成配置预览、加 `--apply` 备份并合并，再用 `iosctl opencode doctor` 验证惰性握手和清单。OpenCode iOS 的 `opencode-ios-bridge` 提供同一入口；具体路径、root/mobile 身份和验证范围见仓库 [集成说明](../../../docs/opencode-integration.md)。doctor 不连接手机，不证明截图已送达模型。

手机上的 OpenCode 2.2.5 使用其实际 `debug paths` / `debug config` 找到的用户目录配置；不要套用电脑上的 Windows 路径。当前设备通过自己的 Wi-Fi 地址连接既有插件，回环地址未监听；地址与配对文件留在私有本地配置中。使用 `opencode reload` 后检查手机自己的 `opencode mcp list`，不能用电脑端的 connected 代替手机端验收。
