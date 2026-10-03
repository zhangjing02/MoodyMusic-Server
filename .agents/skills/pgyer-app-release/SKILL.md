---
name: pgyer-app-release
description: >-
  音信 (MoodyMusic) Android 客户端版本发布与蒲公英上架工作流。
  当用户提出「发布版本」、「打包上线」、「发版」、「发新版」、「打包上传蒲公英」、「构建发布包」等诉求时触发。
  负责版本号与构建号管理、Gradle 正式环境构建（assembleRelease）、以及通过 OpenAPI 直传发布到蒲公英平台。
---

# 音信 Android 蒲公英发布 Skill

本 Skill 规范了音信（MoodyMusic）从版本修改、正式签名打包到蒲公英平台自动发布的完整流水线。

---

## 一、触发条件与交互原则

1. **用户未指定版本号时**：
   - 首先读取 `MoodyMusicForAndroid/app/build.gradle.kts` 获取当前 `versionName` 与 `versionCode`。
   - 主动询问用户本次发布的版本号（例如推荐次版本号，如当前是 `1.0.1` 则推荐 `1.0.2`）以及本次版本更新说明。
2. **用户已明确指定版本号时**（例如：“帮我发个 1.0.2 版本并上传蒲公英”）：
   - 无需多余询问，直接按照用户指定的版本号全自动执行打包与上架。

---

## 二、标准执行流程

### 步骤 1：修改 Gradle 版本配置
定位文件：`MoodyMusicForAndroid/app/build.gradle.kts`
- `versionName = "<新版本号>"`（如 `"1.0.3"`）
- `versionCode` 递增（在当前数值基础上 +1）

### 步骤 2：智能生成版本更新说明（必选内容）
- 自动分析 Git 工作区与近期提交变动（`git diff`、`git log`），总结本次发版的核心改动与体验升级，提炼为简短精炼的更新说明（Release Notes）。
- 若用户主动提供了更新文案，优先采纳并融合。
- 最终生成的更新文案必须注入到步骤 4 上传脚本中，作为 `buildUpdateDescription` 返回给客户端「版本与更新」接口展示。

### 步骤 3：编译签名正式包 (Release APK)
在 `MoodyMusicForAndroid` 目录下执行编译命令：
```powershell
./gradlew :app:assembleRelease
```
- **产物目标**：`app/build/outputs/apk/release/app-release.apk`
- 确保构建退出码为 `0`，并核验生成文件大小（通常约 20~22 MB 左右）。

### 步骤 4：调用脚本直传蒲公英并联动极光静默推送
在 `MoodyMusicForAndroid` 目录下运行 Node.js 发布脚本：
```powershell
node scripts/upload_pgyer.mjs "app/build/outputs/apk/release/app-release.apk" "更新说明文案"
```
*注：脚本位于 [scripts/upload_pgyer.mjs](../../MoodyMusicForAndroid/scripts/upload_pgyer.mjs)，上传成功后会自动调用极光 OpenAPI 向所有在线 App 发送静默更新透传指令（`APP_VERSION_UPDATE`），驱动客户端后台刷新版本状态流，拉开抽屉即显小红点。*

### 步骤 5：反馈发布结果与交付物
向用户展示标准发布卡片：
- **版本名称**：如 `v1.0.2`
- **构建编号**：如 `Build 4 (versionCode 3)`
- **安装主页**：https://www.pgyer.com/yinxin-android
- **更新说明**：用户指定或默认的更新描述
- **包体大小**：如 `21.0 MB`
