from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files("flet")
binaries = collect_dynamic_libs("flet")
hiddenimports = []
