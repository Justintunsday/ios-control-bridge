# 文件系统定位

## 路径地图

这些是候选位置，使用 `ls -ld`、当前用户信息和容器元数据核实存在性与权限。

| 路径/对象 | 用途与定位要点 |
| --- | --- |
| `/`、`/System`、Apple 的 `/usr` | 系统文件。现代系统卷存在完整性保护；查询任务无需重新挂载或关闭保护。 |
| `/var`、`/private/var` | 常见为同一数据树的别名；用符号链接和物理路径去重。 |
| `/var/mobile` | 常见 mobile 用户 HOME；同时核实会话的 `$HOME` 与 UID。 |
| `/var/mobile/Documents` | 终端工具和用户文档的常见位置，不代表“文件”App 中所有文件。 |
| `/var/mobile/Downloads` | 可存在的下载目录；实际也可能位于应用容器或文件提供程序。 |
| `/var/mobile/Library/Preferences` | 用户偏好设置。只针对目标 plist 的必要字段查询。 |
| `/var/mobile/Library/Logs/CrashReporter` | 常见崩溃/诊断报告位置；版本与工具可能提供其他路径。 |
| `/var/mobile/Media` | 媒体相关数据；从明确的相册/文件请求确定子目录。 |
| `/var/containers/Bundle/Application/<UUID>` | 第三方应用 bundle 候选位置；`Info.plist` 中的 bundle identifier 用于识别应用。 |
| `/var/mobile/Containers/Data/Application/<UUID>` | 应用数据容器候选位置，包含该应用的 Documents、Library、tmp。 |
| `/var/mobile/Containers/Shared/AppGroup/<UUID>` | App Group 共享容器；不能仅凭 UUID 推断所有者。 |
| `/var/mobile/Library/Mobile Documents` | iCloud 文档相关本地位置；文件提供程序与占位文件会影响内容可用性。 |
| `/Library/LaunchDaemons`、`/System/Library/LaunchDaemons` | launchd 配置候选位置；存在配置文件不等于服务已加载或运行。 |
| `/var/jb` | 常见 rootless bootstrap 入口，可能是符号链接。 |
| `/var/jb/usr/bin`、`/var/jb/Library`、`/var/jb/etc` | 常见 rootless 越狱命令、扩展、配置目录；以实测前缀为准。 |
| `/private/preboot` | 部分 rootless 的实际存放位置；通过已知链接解析，不遍历并猜测活动 bootstrap。 |

Apple 的应用目录约定：Documents 放用户文档，Library 放应用支持和缓存等数据，tmp 放临时数据。这个约定解释容器内部用途；容器绝对路径与 UUID 仍需设备侧核实。[Apple 文件系统文档](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)

## rootful、rootless 与重定位

- **rootful**：越狱软件可能使用传统 `/usr`、`/Library`、`/etc` 路径；`/var/jb` 缺失本身不足以确定类型。
- **rootless**：常见安装前缀为 `/var/jb`。bootstrap 的实际路径可重定位；工具路径、链接解析及包管理器证据要一起看。[Theos rootless 文档](https://theos.dev/docs/rootless)
- **重定位/RootHide 类环境**：使用其已安装的路径解析能力和当前工具返回的前缀，不硬编码随机目录名，也不把普通 rootless 包视为必然兼容。
- `dpkg --print-architecture`、`dpkg-query` 可提供包架构和来源证据；不要仅凭 CPU 为 arm64 就安装任意 arm64 包。
- Apple 的 `/var/mobile` 应用数据通常沿用 Apple 数据路径。只对属于越狱软件的逻辑路径应用已确认的 bootstrap 前缀。

## 查文件的决策

1. 从用户说的应用、文件类型、名称和时间确定最小相关位置。普通文档先找 Documents/Downloads，再按线索找应用容器或文件提供程序。
2. 检查目录权限和是否为符号链接，再进行有深度和时间限制的查询。工具支持 `-maxdepth`、`-iname`、`-print0` 与否须确认。
3. 需要关联 bundle ID 时，只读取相关容器的 `Info.plist` 或 `.com.apple.mobile_container_manager.metadata.plist` 等已发现元数据；`MCMMetadataIdentifier` 可作为线索。读取失败不等于该应用未安装。
4. UUID 会随重装/恢复改变；旧记录只能作为检索线索。输出当前绝对路径、大小和时间。
5. 文件名含空格、引号、中文或换行时，使用参数化接口或 NUL 分隔方式。仅用于展示的逐行结果不能直接作为批量修改清单。

“没有找到”需要明确范围。权限拒绝、iCloud 内容尚未下载、文件提供程序未暴露本地文件、搜索超时和输出截断各有不同含义。

## 权限与正文

先用 `id` 和 `ls -ld` 区分 Unix 权限、容器可见性、数据保护和 entitlement 限制。设备锁定可能影响受保护内容。按用户请求使用现有权限；无法读取时描述具体错误。

元数据查询只读取文件名、类型、大小、时间和目标 plist 必要键。读取数据库时使用兼容的只读接口并考虑 WAL/快照一致性；不要直接改写应用数据库或把聊天、位置、令牌等无关正文作为训练材料。

复核日期：2026-11-04。绝对路径为候选，设备事实优先。
