[app]
title = QUINTE-X
package.name = quintex
package.domain = org.xavpro
source.dir = .
source.include_exts = py,png,jpg,kv,json
version = 0.1.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0

# Permissions
android.permissions = INTERNET

# Targeting Android moderne
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# Données embarquées (le JSON top5 voyage avec l'APK pour la démo)
# Si tu veux que l'app fetch depuis GitHub, change find_data_file() dans main.py
android.add_assets = quinte_x_top5.json

[buildozer]
log_level = 2
warn_on_root = 1
