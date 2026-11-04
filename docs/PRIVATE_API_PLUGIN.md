# 私有 API 插件与 Sileo 包

本文记录私有 API snapshot 插件在 Sileo/dpkg 中的身份，并与仓库元数据保持一致。

## 包信息

| 字段 | 值 |
| --- | --- |
| Package ID | `com.opencode.sbsnapshot` |
| Name | `iOS Control Bridge - Private API Snapshot` |
| Version | `0.5` |
| Architecture | `iphoneos-arm64` |
| Section | Development |
| Depends | `ellekit` |
| Maintainer | `Justintunsday <Justintunsday@users.noreply.github.com>` |
| Author | `iOS Control Bridge contributors` |
| Homepage | https://github.com/Justintunsday/ios-control-bridge |
| 安装 README | `/var/jb/usr/share/doc/com.opencode.sbsnapshot/README.md` |

## 载荷

```text
/var/jb/usr/lib/TweakInject/sbsnapshot.dylib
/var/jb/usr/lib/TweakInject/sbsnapshot.plist
/var/jb/usr/share/doc/com.opencode.sbsnapshot/README.md
```

## 说明

- 这是 review-only 的 passive C-runtime snapshot helper，用于 `SBActivityManager` / Live Activity 调查。
- 不提供任意 selector 执行；没有网络监听。
- 包 ID 保持 `com.opencode.sbsnapshot` 以保留升级路径；Sileo 显示名、Maintainer、Author、Homepage、README 已同步到 `ios-control-bridge` 仓库身份。
- Sileo 如果仍显示旧缓存，刷新包列表或重新打开 Sileo；已安装状态由 dpkg 提供，当前版本为 0.5。

## 相关

- 项目 README：https://github.com/Justintunsday/ios-control-bridge/blob/main/README.md
- 私有 API skill 参考：`skills/ios-control-bridge/references/private-apis.md`
