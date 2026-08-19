"""Services Layer — Modularized domain-driven services for XenRay."""

from __future__ import annotations

from src.services.connection import (
    PRIORITY_IMPORT,
    PRIORITY_INTERVAL,
    PRIORITY_MANUAL,
    ConnectionOrchestrator,
    ConnectionTester,
    DnsConfigurator,
    LatencyTester,
    NetworkValidator,
    PingManager,
    RouteManagerService,
    ServerInspector,
    TunDnsService,
    TunInjector,
    ping_manager,
    server_inspector,
)
from src.services.core_engines import (
    ConfigPatcher,
    LegacyConfigService,
    SingboxProcessManager,
    SingboxService,
    XrayConfigProcessor,
    XrayProcessManager,
    XrayService,
    config_utils,
    get_server_object,
    is_ip,
)
from src.services.installer import (
    AppUpdateService,
    ArchiveExtractor,
    FileDownloader,
    RuleUpdateService,
    XrayInstallerService,
    XrayVersionChecker,
)
from src.services.monitoring import (
    ActiveConnectivityMonitor,
    AutoReconnectService,
    ConnectionMonitoringService,
    CoreHealthMonitor,
    MonitorSignal,
    NetworkStatsService,
    PassiveLogMonitor,
    XrayLogWatcher,
)
from src.services.system import (
    LanService,
    is_supported,
    is_task_registered,
    lan_service,
    register_task,
    unregister_task,
)

__all__ = [
    # Connection
    "ConnectionOrchestrator",
    "ConnectionTester",
    "LatencyTester",
    "PingManager",
    "ping_manager",
    "PRIORITY_MANUAL",
    "PRIORITY_IMPORT",
    "PRIORITY_INTERVAL",
    "ServerInspector",
    "server_inspector",
    "NetworkValidator",
    "RouteManagerService",
    "DnsConfigurator",
    "TunDnsService",
    "TunInjector",
    # Core Engines
    "XrayService",
    "XrayProcessManager",
    "SingboxService",
    "SingboxProcessManager",
    "XrayConfigProcessor",
    "ConfigPatcher",
    "config_utils",
    "is_ip",
    "get_server_object",
    "LegacyConfigService",
    # Installer
    "XrayInstallerService",
    "FileDownloader",
    "ArchiveExtractor",
    "XrayVersionChecker",
    "AppUpdateService",
    "RuleUpdateService",
    # Monitoring
    "ConnectionMonitoringService",
    "ActiveConnectivityMonitor",
    "PassiveLogMonitor",
    "CoreHealthMonitor",
    "AutoReconnectService",
    "NetworkStatsService",
    "XrayLogWatcher",
    "MonitorSignal",
    # System
    "LanService",
    "lan_service",
    "is_task_registered",
    "register_task",
    "unregister_task",
    "is_supported",
]
