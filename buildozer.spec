[app]
title = 数字分析工具
package.name = numberanalysis
package.domain = org.lan7788alex
source.dir = .
source.include_exts = py,txt,png,jpg,kv,atlas,ttf,otf,ttc
version = 2.0

requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.0,pyjnius

orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 24
android.ndk_api = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.debug_artifact = apk

p4a.branch = v2024.01.21
p4a.bootstrap = sdl2

# Android 10+ 保存 Download 使用 MediaStore，不需要存储权限。
# 低版本保留写外部存储权限兼容路径。
android.permissions = WRITE_EXTERNAL_STORAGE

[buildozer]
log_level = 2
warn_on_root = 1
