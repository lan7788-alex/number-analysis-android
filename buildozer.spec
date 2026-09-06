[app]
title = 数字分析工具
package.name = numberanalysis
package.domain = org.lan7788alex
source.dir = .
source.include_exts = py,txt,png,jpg,kv,atlas,ttf,otf,ttc
version = 1.5

# Python/Kivy：固定到 p4a 2024.01.21 对应的 Python 3.11 体系
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.0,pyjnius

orientation = portrait
fullscreen = 0

# Android
android.api = 35
android.minapi = 24
android.ndk_api = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.debug_artifact = apk

# python-for-android：固定到默认 Python 3.11 的稳定版本
p4a.branch = v2024.01.21
p4a.bootstrap = sdl2

# 离线软件，不申请联网权限
android.permissions = WRITE_EXTERNAL_STORAGE

[buildozer]
log_level = 2
warn_on_root = 1
