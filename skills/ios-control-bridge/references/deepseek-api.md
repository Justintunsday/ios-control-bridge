# 移动端 OpenCode 的 DeepSeek API 失效排查

本文件记录已经验证过的移动端 OpenCode / DeepSeek 故障处理流程。先判断失败发生在 **provider / 模型选择**、**运行中的 server 缓存**，还是 **key 本身**；不要直接重装或反复重填 key。

## 1. 先区分官方 DeepSeek 与免费网关

- 官方 DeepSeek 模型：`deepseek/deepseek-flash`，使用 DeepSeek 官方 API key。
- `opencode/*-free`（例如 `opencode/deepseek-v4.1-flash-free`）是 OpenCode 的免费网关，有独立凭据和额度；替换 DeepSeek 官方 key 不会修复免费网关的认证失败。
- 典型错误：
  - `Authentication Fails, Your api key: ****626e is invalid`
  - `DEEPSEEK_API_KEY is not set`
  - `provider.auth`
- 先比较报错中的 key 尾号与当前 key 尾号：
  - 尾号不同：server/App 还在使用旧 key，见第 3 节。
  - 尾号相同但 401/403：key 已被删除、封禁、额度/地区限制，见第 4 节。
  - 模型名带 `free`：先切换到官方 `deepseek/deepseek-flash`，不要继续排查 DeepSeek key。

## 2. Key 存放位置与启动脚本

移动端已验证的路径：

```text
/var/jb/var/root/.config/opencode-root/deepseek-api-key    root 600
/var/mobile/.config/opencode-root/deepseek-api-key         mobile 600
```

两个启动脚本会在每次启动时读取 key 并导出 `DEEPSEEK_API_KEY`：

```text
/var/jb/usr/bin/opencode
/var/jb/usr/local/libexec/opencode-root-server
```

不要修改 App bundle；只改上述启动脚本和 key 文件。不要在任何日志、技能文本、仓库或对话中写入完整 key；只允许比较尾号或长度。

OpenCode 的凭据数据库是另一个来源：

```sh
sudo opencode auth list
sudo opencode auth export   # 只在本地安全处理，不输出完整 key
```

正常情况下只保留一把有效的 DeepSeek 凭据，并设为 active。旧凭据会让 App 随机选中失效 key。

## 3. 标准修复顺序

1. 先验证 key 是否真的有效：请求 DeepSeek 余额接口，检查 HTTP 200 和 `is_available: true`；不要把 key 打印到输出。
2. 更新上面两个 key 文件（600，root/mobile 各一份）。
3. 清理旧凭据：
   - 用 `opencode auth logout deepseek "<旧标签>"` 删除失效账号。
   - 如需非交互导入，使用 `opencode auth import` 的 JSON 数组格式：`id`、`integrationID: "deepseek"`、`label`、`active: true`、`value: {"type": "key", "key": "..."}`；导入后用 `opencode auth switch deepseek "<标签>"` 激活。
4. 重启服务：
   - root server：`sudo launchctl kickstart -k system/com.opencode.root-server`
   - 后台服务：`sudo opencode service stop && sudo opencode service start`
   - 如果 App 使用自己的移动端 server，结束旧的 `opencode.mjs serve --service` 进程，让 App 重开时重新启动。
5. **强制关闭并重新打开 App，新 session**。已打开的 App/会话会缓存旧 key，重启服务不会替换已连接会话的凭据。
6. 用短提示验证，例如 `Reply with exactly OK and nothing else`。在拿到实际响应前不要报告已修复。

## 4. 仍然失败时

- 报错尾号仍是旧 key：App 仍有自己的旧 server、旧 session 或 App 内单独保存的 key；重启/结束 server 后强制重开 App，必要时在 App 的 provider/API key 设置中替换。
- 报错尾号是新 key、HTTP 401/403：DeepSeek 账号侧问题（key 被删除/封禁/风控/地区限制），本地配置无法修复；轮换 key 或联系服务商。
- HTTP 402/余额不足：检查 DeepSeek 控制台账单，不是 OpenCode 问题。
- HTTP 429：限流或额度，降低并发/自动重试，等待冷却。
- 卡住无响应：先用 `opencode run --standalone` 验证同一 key；standalone 可用说明 key 有效，问题在 server/App 连接和认证密码，不应反复重填 key。
- root server 与 service 是两个不同的进程/端口；`opencode service status` 显示的是后台服务地址，root server 使用 launchd 标签 `com.opencode.root-server`。不要混用两者的密码。

## 5. 安全与稳定性约定

- key 只放 600 权限文件；不要写死到技能、仓库或脚本中。
- key 出现在聊天/日志中后，视为可能泄露，按需在服务商控制台轮换。
- 不保留多把失效 DeepSeek 凭据，避免 OpenCode 选错账号。
- 不在多个设备/多端同时共用同一 key；免费网关与官方 API 不要混用同一个模型入口。
- 修改启动脚本前保留备份；技能只记录可复现、已验证的路径和流程，不记录具体 key、密码或设备私有令牌。
