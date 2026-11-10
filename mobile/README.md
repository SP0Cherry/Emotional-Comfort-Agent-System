# 慢慢说 · Android 客户端

Flutter Android MVP，与仓库中 FastAPI 的 `/v1` 契约配套。已实现验证码登录、人物照片/表达习惯/授权例句、隔离试聊、会话历史、文字聊天、SSE 恢复/状态轮询、停止/重试、长期记忆管理、资料导出、异步清空与退出登录。语音输入和朗读属于第二阶段。

## 运行

安装 Flutter stable（Flutter ≥ 3.47、Dart ≥ 3.13）、Android SDK、JDK 17。启动项目后端 API 和 Worker，然后在本目录运行：

```powershell
flutter pub get
flutter analyze
flutter test
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` 是 Android 模拟器访问宿主机的地址。真机请使用同一局域网中的电脑地址，并允许端口 8000 的局域网访问。开发后端返回的 `development_code` 会显示在登录页面；生产短信模式不返回此字段。

Android 最低 API 24。工程包含与当前 Flutter Android 模板一致的 Gradle 9.3.1 / AGP 9.1.0 / Kotlin 2.4.0 配置、Gradle wrapper、Kotlin MainActivity、启动主题和原生 JSON 保存对话框。HTTP 仅在 debug manifest 开放。release 必须显式指定 HTTPS：

```powershell
flutter build apk --release --dart-define=API_BASE_URL=https://your-api.example
```

发布者需在 Android 工程配置自己的正式签名；仓库不包含签名密钥，也不会自动使用 debug 密钥签署 release。首次构建由 Flutter 写入忽略的 `android/local.properties`。当前平台工程针对 Android；iOS 尚未配置。

## 恢复与隐私

- 安全存储仅保存令牌。普通偏好仅保存字号、人物/会话/run/幂等 ID、事件游标和清理操作 ID，不保存聊天正文、照片或草稿。Android 备份已关闭。
- 单次网络重发与 401 自动刷新保持同一 `client_message_id`。用户点击失败任务的“重试这次回复”调用专门 retry 接口，生成新 ID，服务器复用原用户消息。
- 任务状态每 5 秒查询一次；SSE 断线按 1/2/4/8 秒加抖动重连原 run。前台恢复先取权威快照，再订阅；410 回放过期也使用快照恢复。
- 事件用有状态 UTF-8 解码和逐行 SSE 解析；仅空行提交完整事件。重复 seq 丢弃；消息按服务端 ID 替换、seq 排序，避免重复聊天气泡。
- 手机进程终止后从服务器恢复历史和活动 run。若在首次提交确认前终止且服务端未收到消息，由于正文不落盘，需用户重新输入；若已收到则通过会话的 active/latest run 找回。未确认正文不会静默重发。
- “结束对话”停止当前生成并返回列表；历史保留。新对话从历史页创建。“从长期记忆中移除”保留原聊天；完整清除入口位于设置，清理期间人物暂停使用。
- 导出经 Android 系统文件选择器保存 JSON，无需广泛存储权限。导出文件含个人资料，保存前明确提示用户。

## 验证

`test/sse_test.dart` 覆盖每个字节切分位置、多行、心跳、BOM、截断帧、重放去重与终态；`test/network_test.dart` 覆盖并发 401 单次轮换和幂等请求重发；`test/chat_recovery_test.dart` 覆盖不确定发送的 ID 保留、正文不缓存、历史合并和断线重连原任务；`test/login_flow_test.dart` 覆盖验证码请求、原挑战校验及登录后的页面跳转。

本次已完成依赖解析与 `pubspec.lock`、`flutter analyze --no-pub`（无问题）、`flutter test --no-pub`（9 项通过）。使用项目本地引导的 Flutter stable 源码及 Dart 3.13.5；工具链目录属于忽略的开发缓存，不随工程交付。已尝试 debug APK 构建，但当前机器缺少 Android SDK，工具报告 `No Android SDK found`，因此未生成 APK，原生构建与真机验收仍待安装 Android 工具链后执行。

真机验收：登录 → 上传照片建人物 → 试聊 → 正式发送 → 断网重连 → 停止/重试 → 新会话 → 确认/编辑/移除记忆 → JSON 导出 → 全量清理 → 退出。请在系统字号调大、横屏、照片选择导致 Activity 重建时复测。尚未完成真机和 APK 验收的环境不能视为已交付可安装包。

实现参考：[Flutter Android 配置](https://docs.flutter.dev/deployment/android)、[Dio](https://pub.dev/packages/dio)、[image_picker](https://pub.dev/packages/image_picker)、[flutter_secure_storage](https://pub.dev/packages/flutter_secure_storage)。
