[app]
title = 数字分析工具
package.name = numberanalysis
package.domain = org.lan7788alex
source.dir = .
source.include_exts = py,txt,png,jpg,kv,atlas
version = 1.2
requirements = python3,kivy
orientation = portrait
fullscreen = 0

# Android
android.api = 35
android.minapi = 24
android.ndk_api = 24
android.ndk = 28c
android.archs = arm64-v8a
android.accept_sdk_license = True

# 离线软件，不申请联网权限
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
