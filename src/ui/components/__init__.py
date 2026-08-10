"""UI components package exporting all page-categorized components."""

from src.ui.components.chain import ChainListItem, ChainNodeRow
from src.ui.components.common import (
    AdminRestartDialog,
    AppContainer,
    CloseDialog,
    Header,
    NavSidebar,
    PageHeader,
    Toast,
    ToastManager,
)
from src.ui.components.dashboard import (
    ConnectionButton,
    ConnectionGuideCard,
    MetricCard,
    ServerCard,
    StatusDisplay,
    TimerDisplay,
    TrafficCards,
    TrafficChartComponent,
    WaveVisualizer,
)
from src.ui.components.dns import DNSServerRow
from src.ui.components.lan import LanSharingCard, MicroChip, QRCard
from src.ui.components.logs import LogsDrawer, LogViewer, TerminalWindow
from src.ui.components.routing import RoutingToggleRow, RuleItemRow
from src.ui.components.servers import (
    AddServerDialog,
    ServerList,
    ServerListHeader,
    ServerListItem,
    ServerSearchBar,
    SubscriptionListItem,
)
from src.ui.components.settings import (
    AutoReconnectToggleRow,
    BentoCard,
    CipherSuitesInputRow,
    CoreDropdownRow,
    CountryDropdownRow,
    HttpPortInputRow,
    LanguageDropdownRow,
    LanShareToggleRow,
    ModeSwitchRow,
    PortInputRow,
    SectionHeader,
    SettingsDrawer,
    SettingsListTile,
    SettingsRow,
    SettingsSection,
    StartupToggleRow,
    TunEngineDropdownRow,
    TunEngineRow,
    UpdateCard,
)
from src.ui.components.statistics import StatCard, StatsHeader, WaveCard

__all__ = [
    # Dashboard
    "ConnectionButton",
    "ConnectionGuideCard",
    "MetricCard",
    "ServerCard",
    "StatusDisplay",
    "TimerDisplay",
    "TrafficCards",
    "TrafficChartComponent",
    "WaveVisualizer",
    # Servers
    "AddServerDialog",
    "ServerList",
    "ServerListHeader",
    "ServerListItem",
    "ServerSearchBar",
    "SubscriptionListItem",
    # Logs
    "LogViewer",
    "LogsDrawer",
    "TerminalWindow",
    # Settings
    "AutoReconnectToggleRow",
    "BentoCard",
    "CipherSuitesInputRow",
    "CoreDropdownRow",
    "CountryDropdownRow",
    "HttpPortInputRow",
    "LanShareToggleRow",
    "LanguageDropdownRow",
    "ModeSwitchRow",
    "PortInputRow",
    "SectionHeader",
    "SettingsDrawer",
    "SettingsListTile",
    "SettingsRow",
    "SettingsSection",
    "StartupToggleRow",
    "TunEngineDropdownRow",
    "TunEngineRow",
    "UpdateCard",
    # LAN
    "LanSharingCard",
    "MicroChip",
    "QRCard",
    # Chain
    "ChainListItem",
    "ChainNodeRow",
    # Common
    "AdminRestartDialog",
    "AppContainer",
    "CloseDialog",
    "Header",
    "NavSidebar",
    "PageHeader",
    "Toast",
    "ToastManager",
    # Routing
    "RoutingToggleRow",
    "RuleItemRow",
    # DNS
    "DNSServerRow",
    # Statistics
    "StatCard",
    "StatsHeader",
    "WaveCard",
]
