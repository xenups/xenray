# PyInstaller hook for dependency_injector string-based imports
# This hook automatically collects modules referenced as strings in the DI container

from PyInstaller.utils.hooks import collect_submodules

# Collect all submodules from src.ui.handlers and src.ui.managers
# These are often referenced as strings in the DI container
hiddenimports = []

# Collect UI handlers
hiddenimports += collect_submodules('src.ui.handlers')

# Collect UI managers  
hiddenimports += collect_submodules('src.ui.managers')

# Collect services that might be lazy-loaded
hiddenimports += collect_submodules('src.services')

# Main window
hiddenimports += ['src.ui.main_window']
