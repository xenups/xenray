"""Standardized UI Pages package."""

from src.ui.pages.chain_builder_page import ChainBuilderPage
from src.ui.pages.dashboard_page import DashboardPage, DashboardView
from src.ui.pages.dns_page import DNSPage
from src.ui.pages.lan_sharing_page import LanSharingPage, LanSharingView
from src.ui.pages.logs_page import LogsPage, LogsView
from src.ui.pages.routing_page import RoutingPage
from src.ui.pages.servers_page import ServersPage, ServersView
from src.ui.pages.settings_page import SettingsPage, SettingsView
from src.ui.pages.statistics_page import StatisticsPage, StatisticsView

__all__ = [
    "DashboardPage",
    "DashboardView",
    "LogsPage",
    "LogsView",
    "SettingsPage",
    "SettingsView",
    "ServersPage",
    "ServersView",
    "StatisticsPage",
    "StatisticsView",
    "LanSharingPage",
    "LanSharingView",
    "RoutingPage",
    "DNSPage",
    "ChainBuilderPage",
]
