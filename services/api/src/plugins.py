"""
Plugin interface definition for future extensibility.

Defines the abstract base for plugins and a simple registry.
No full plugin system required — this establishes the interface
for future integration (e.g., Plex, Jellyfin, external health monitors).
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class MilestonePlugin(ABC):
    """Base class for Milestone plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin display name."""
        ...
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string."""
        ...
    
    @property
    def description(self) -> str:
        """Plugin description."""
        return ""
    
    async def on_startup(self) -> None:
        """Called when the application starts."""
        pass
    
    async def on_shutdown(self) -> None:
        """Called when the application shuts down."""
        pass
    
    async def on_scan_complete(self, stats: dict) -> None:
        """Called after a scan completes."""
        pass
    
    async def on_copy_complete(self, operation: dict) -> None:
        """Called after a copy operation completes."""
        pass
    
    async def on_item_discovered(self, item: dict) -> None:
        """Called when a new media item is discovered."""
        pass


class ExternalHealthMonitor(MilestonePlugin):
    """Example plugin: external drive health monitoring."""
    
    @property
    def name(self) -> str:
        return "External Health Monitor"
    
    @property
    def version(self) -> str:
        return "0.1.0"
    
    @property
    def description(self) -> str:
        return "Monitors drive health via S.M.A.R.T. data"
    
    async def get_drive_health(self, drive_path: str) -> Optional[dict]:
        """Query drive health status. Override with actual implementation."""
        return {
            "status": "unknown",
            "message": "Health monitoring not configured",
        }


# Plugin registry
_plugins: list[MilestonePlugin] = []


def register_plugin(plugin: MilestonePlugin) -> None:
    """Register a plugin instance."""
    _plugins.append(plugin)
    logger.info(f"Plugin registered: {plugin.name} v{plugin.version}")


def get_plugins() -> list[dict]:
    """Get info about registered plugins."""
    return [
        {
            "name": p.name,
            "version": p.version,
            "description": p.description,
        }
        for p in _plugins
    ]


async def emit_event(event: str, **kwargs) -> None:
    """Emit an event to all registered plugins."""
    for plugin in _plugins:
        handler = getattr(plugin, event, None)
        if handler and callable(handler):
            try:
                await handler(**kwargs)
            except Exception as e:
                logger.error(f"Plugin {plugin.name} error on {event}: {e}")
