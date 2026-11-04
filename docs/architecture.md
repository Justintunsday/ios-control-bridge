# 架构与接口

运行路径：客户端 → 本机 `iosctl` → 操作注册表 → 服务适配器 → iOS 系统能力 / 网络数据源。客户端可以是终端、AI 工具调用器或未来的语音入口；设备能力与模型、对话服务、SSH 账号分离。

`src/ios_control_bridge` 是 Python 3.9+ 核心。`native/<service>` 放置需要 Apple runtime 的原生适配器。`tools/build_native.py` 只调用已存在的编译器和 SDK，在本仓库 `build/native` 内生成 helper。`skills/ios-control-bridge` 提供可单独安装的指令入口。

## 请求

```json
{
  "operation": "activities.get",
  "request_id": "debd4d72-1860-4d98-a3d0-c026ddbd1744",
  "params": {"activity_id": "1DF0A9B7-6211-4FD8-A80A-03BEF357532A", "timeout_ms": 5000}
}
```

对应 CLI：`iosctl call OPERATION --params JSON --request-id UUID`。CLI 不提供任意命令执行接口。请求 schema 在 `schemas/request.schema.json`；该文件定义客户端契约，当前交付的执行入口是本机 CLI，尚未启动 HTTP 或 MCP 服务。

## 返回与实际来源

返回 schema 在 `schemas/result.schema.json`。`observed_at` 是此次适配器处理结果的时间，系统自己的数据时间保留在 `data` 中；两者不互相替代。`complete_for_scope` 只覆盖明确的操作和选择范围。`capabilities` 的来源为能力声明加执行环境探测，不代表已查询所有系统服务。

退出码 0 = verified、2 = partial、3 = unavailable、4 = error。对实时活动，完整响应中 `target_found:false`、`activity:null` 是目标在当前可读范围内不存在；超时没有正文，不能当成活动结束。

读取器的原生结果保存在 `data`，保留活动 ID、原始状态、正文编码、系统服务和采样时间。Python 边界校验 JSON schema 标识、来源、目标 ID、退出码与状态的一致性，不从历史文件补正文。

## 写操作的实现约束

写服务目前处于计划阶段。实现时，每个操作拥有固定参数和值范围、确切的设备目标、有限超时及修改后的读取验证。记录读回值和未完成的验证，区分“请求已受理”和“结果已核实”。沿用用户已有授权；不要求用户重复确认已经明确交代的操作。

单次 CLI 查询不等于常驻监测。持续任务需要后续独立运行器管理生命周期、连接中断、停止条件和通知；目前没有部署常驻服务。
