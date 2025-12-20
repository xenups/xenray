"""Dependency Injection Container for XenRay application."""
from dependency_injector import containers, providers

from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.services.network_stats import NetworkStatsService
from src.ui.managers.monitoring_service import MonitoringService
from src.ui.managers.profile_manager import ProfileManager


class ApplicationContainer(containers.DeclarativeContainer):
    """DI Container for application-wide dependencies."""

    # Configuration
    wiring_config = containers.WiringConfiguration(
        modules=[
            "src.ui.main_window",
            "src.ui.handlers.connection_handler",
        ]
    )

    # Core services (singletons)
    config_manager = providers.Singleton(ConfigManager)

    connection_manager = providers.Singleton(
        ConnectionManager,
        config_manager=config_manager,
    )

    network_stats = providers.Singleton(NetworkStatsService)


# Factory functions for managers (these need MainWindow dependencies)
def create_profile_manager(container, connection_handler, ui_updater):
    """Factory for ProfileManager."""
    return ProfileManager(
        connection_manager=container.connection_manager(),
        connection_handler=connection_handler,
        ui_updater=ui_updater,
    )


def create_monitoring_service(container, connection_handler, ui_updater, toast_manager):
    """Factory for MonitoringService."""
    return MonitoringService(
        connection_manager=container.connection_manager(),
        connection_handler=connection_handler,
        ui_updater=ui_updater,
        toast_manager=toast_manager,
    )
