# App 安装与删除

先运行 `iosctl capabilities --service apps`。支持边界为 iOS 16.1.1 / 20B101，
需要 `build/native/icb-apps`。`ICB_APPS_HELPER` 可指定已有部署路径。

| 任务 | 固定操作与关键参数 |
| --- | --- |
| 找到 App 的准确 ID | `apps.list {"query":"名称","limit":20}`；支持 `offset`、`include_system` |
| 查询实际状态 | `apps.get {"bundle_id":"com.example.app"}` |
| 查询 App Store | `apps.store_info {"app_id":"数字ID"}`，也可使用 `url` 指向 apps.apple.com 的 App 链接 |
| App Store 下载 | `apps.download {"source":"app_store","app_id":"数字ID","verify_timeout_ms":60000}` |
| 本地 IPA | `apps.install {"path":"/绝对路径/App.ipa"}` |
| IPA 链接 | `apps.download {"source":"ipa","url":"https://实际域名/App.ipa"}` |
| 删除 | `apps.uninstall {"bundle_id":"准确ID"}` |

IPA 默认使用 `installer: "system"`，要求系统接受其签名；手机已经安装
TrollStore 时，可显式指定 `installer: "trollstore"`，以 root 执行。
对应 TrollStore App 的删除也显式指定此渠道。不自动安装依赖，不在一次
拒绝或超时后自动改渠道重试。更新已有 App 需要明确 `replace: true`。
IPA 可附带预期 `bundle_id` 和 `sha256`；下载必须全程 HTTPS。

App Store 使用 Apple 原始免费报价，不接受付费购买或账号密码参数。
后台安装进程最多保留 10 分钟认证上下文（11 分钟硬性期限），CLI 返回
`partial` 后进程仍可等待认证；同一 App 的活动进程持有锁，避免重复下单。
正常系统确认可能要求用户在手机输入 Apple ID 密码或完成生物认证。
`partial/store_download_pending` 表示尚未核实实装；告知用户完成手机提示，
随后调用 `apps.get`，不重复发起下载。用户取消后按实际状态报告。

安装只有独立读回对应 bundle ID、非占位符状态（IPA 还需版本匹配）才是
`verified`。删除需要安装实体和占位符均消失；已不存在时 `changed: false`。
名称、通配符和模糊搜索结果不能直接用于删除；系统 App 及容器外 App 受保护。
安装渠道返回 0 或请求已提交都不等于成功，不能将 `partial` 改写成已完成。

默认下载上限 512 MiB（最多 2 GiB），下载时间 120 秒（可用
`download_timeout_ms` 设为 1–600 秒）；读回 15 秒（可用
`verify_timeout_ms` 设为 0–120 秒）。远程终端的调用期限应覆盖下载和安装；
连接中断后先查询目标状态，避免再次执行结果不明的写入。
