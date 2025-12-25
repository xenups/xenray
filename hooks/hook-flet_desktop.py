from PyInstaller.utils.hooks import collect_all

print("--- LOADING CUSTOM HOOK: flet_desktop ---")

datas, binaries, hiddenimports = collect_all("flet_desktop")
