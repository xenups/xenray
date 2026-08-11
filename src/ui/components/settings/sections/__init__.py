"""Single-responsibility settings sections for the settings drawer.

Each section is a presentational Flet control that composes its own rows and
receives only values + callbacks — no backend services or EventBus wiring.
"""

from src.ui.components.settings.sections.auto_reconnect_section import (
    AutoReconnectSection,
)
from src.ui.components.settings.sections.connectivity_section import ConnectivitySection
from src.ui.components.settings.sections.startup_language_section import (
    StartupLanguageSection,
)
from src.ui.components.settings.sections.updates_section import UpdatesSection

__all__ = [
    "ConnectivitySection",
    "AutoReconnectSection",
    "UpdatesSection",
    "StartupLanguageSection",
]
