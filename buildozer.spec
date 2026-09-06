[app]

title = 数字分析工具
package.name = numberanalysis
package.domain = org.numberanalysis

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt

version = 1.0

requirements = python3,kivy

orientation = portrait

fullscreen = 0

android.archs = arm64-v8a, armeabi-v7a

android.api = 35
android.minapi = 23

android.accept_sdk_license = True


[buildozer]

log_level = 2
warn_on_root = 1
