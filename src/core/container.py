"""Dependency Injection Container for XenRay application."""
from dependency_injector import containers, providers

from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.services.network_stats import NetworkStatsService


class ApplicationContainer(containers.DeclarativeContainer):
    """DI Container for application-wide dependencies."""

    # Configuration
    wiring_config = containers.WiringConfiguration(
        modules=[
            "src.ui.main_window",
            "src.ui.handlers.connection_handler",
        ]
    )

    # ═══════════════════════════════════════════════════════════
    # SINGLETONS - Application-lifetime core services only
    # ═══════════════════════════════════════════════════════════

    config_manager = providers.Singleton(ConfigManager)

    connection_manager = providers.Singleton(
        ConnectionManager,
        config_manager=config_manager,
    )

    systray_handler = providers.Singleton(
        "src.ui.handlers.systray_handler.SystrayHandler",
        connection_manager=connection_manager,
        config_manager=config_manager,
    )

    # ═══════════════════════════════════════════════════════════
    # RESOURCES - Network services (no dependencies on factories)
    # ═══════════════════════════════════════════════════════════

    network_stats = providers.Resource(
        NetworkStatsService,
    )

    network_stats_handler = providers.Resource(
        "src.ui.handlers.network_stats_handler.NetworkStatsHandler",
        network_stats=network_stats,
    )

    # ═══════════════════════════════════════════════════════════
    # FACTORIES - UI-bound, event-driven, no persistent state
    # ═══════════════════════════════════════════════════════════

    connection_handler = providers.Factory(
        "src.ui.handlers.connection_handler.ConnectionHandler",
        connection_manager=connection_manager,
        config_manager=config_manager,
        network_stats=network_stats,
    )

    theme_handler = providers.Factory(
        "src.ui.handlers.theme_handler.ThemeHandler",
        config_manager=config_manager,
    )

    installer_handler = providers.Factory(
        "src.ui.handlers.installer_handler.InstallerHandler",
        connection_manager=connection_manager,
    )

    latency_monitor_handler = providers.Factory(
        "src.ui.handlers.latency_monitor_handler.LatencyMonitorHandler",
        config_manager=config_manager,
    )

    # ═══════════════════════════════════════════════════════════
    # RESOURCES - Defined after factories they depend on
    # ═══════════════════════════════════════════════════════════

    # Background task handler depends on latency_monitor_handler
    background_task_handler = providers.Resource(
        "src.ui.handlers.background_task_handler.BackgroundTaskHandler",
        network_stats_handler=network_stats_handler,
        latency_monitor_handler=latency_monitor_handler,
    )

    # Monitoring service depends on connection_handler
    monitoring_service = providers.Resource(
        "src.ui.managers.monitoring_service.MonitoringService",
        connection_manager=connection_manager,
        connection_handler=connection_handler,
    )

    # ═══════════════════════════════════════════════════════════
    # Additional Singletons (depend on Factories)
    # ═══════════════════════════════════════════════════════════

    # Profile manager depends on connection_handler
    profile_manager = providers.Singleton(
        "src.ui.managers.profile_manager.ProfileManager",
        connection_manager=connection_manager,
        connection_handler=connection_handler,
    )

    # ═══════════════════════════════════════════════════════════
    # FACTORY - Main window (UI root, always factory)
    # ═══════════════════════════════════════════════════════════

    main_window = providers.Factory(
        "src.ui.main_window.MainWindow",
        config_manager=config_manager,
        connection_manager=connection_manager,
        network_stats=network_stats,
        network_stats_handler=network_stats_handler,
        latency_monitor_handler=latency_monitor_handler,
        connection_handler=connection_handler,
        theme_handler=theme_handler,
        installer_handler=installer_handler,
        background_task_handler=background_task_handler,
        systray_handler=systray_handler,
        profile_manager=profile_manager,
        monitoring_service=monitoring_service,
    )
