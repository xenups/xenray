from PyInstaller.utils.hooks import collect_all
print("--- LOADING CUSTOM HOOK: flet ---")

datas, binaries, hiddenimports = collect_all('flet')

# Also ensure flet_runtime is collected as it is often a dependency
d_runtime, b_runtime, h_runtime = collect_all('flet_runtime')

datas += d_runtime
binaries += b_runtime
hiddenimports += h_runtime

# Add flet_desktop to hidden imports to trigger its own hook
hiddenimports.append('flet_desktop')
