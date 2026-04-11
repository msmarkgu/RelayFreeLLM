"""
Provider Registry — auto-discovers and manages provider clients.

Adding a new provider = creating a new XxxClient(ApiInterface) file in api_clients/.
The registry scans the module and registers all ApiInterface subclasses.
"""

import importlib
import inspect
import os
import pkgutil

from .api_clients.api_interface import ApiInterface
from .logging_util import ProjectLogger

logger = ProjectLogger.get_logger(__name__)


class ProviderRegistry:
    """Discovers and manages provider client instances."""

    def __init__(self):
        self._clients: dict[str, ApiInterface] = {}

    def register(self, name: str, client: ApiInterface) -> None:
        """Manually register a provider client."""
        self._clients[name] = client
        logger.info(f"Registered provider: {name}")

    def unregister(self, name: str) -> None:
        """Remove a completely registered client."""
        if name in self._clients:
            del self._clients[name]
            logger.info(f"Unregistered provider: {name}")

    def get_client(self, name: str) -> ApiInterface:
        """Get a registered client by provider name."""
        if name not in self._clients:
            raise ValueError(f"Unknown provider: {name}. Available: {list(self._clients.keys())}")
        return self._clients[name]

    def list_providers(self) -> list[str]:
        """Return all registered provider names."""
        return list(self._clients.keys())

    def all_clients(self) -> dict[str, ApiInterface]:
        """Return the full provider → client mapping."""
        return dict(self._clients)

    def auto_discover(self) -> None:
        """
        Scan the api_clients package and register all ApiInterface subclasses.
        
        Each client must:
          - Subclass ApiInterface
          - Set PROVIDER_NAME to a non-empty string
        """
        clients_pkg_path = os.path.join(os.path.dirname(__file__), "api_clients")
        package_name = "src.api_clients"

        for _, module_name, _ in pkgutil.iter_modules([clients_pkg_path]):
            if module_name.startswith("_") or module_name in ("api_interface", "client_config"):
                continue

            try:
                module = importlib.import_module(f"{package_name}.{module_name}")
            except Exception as e:
                logger.warning(f"Failed to import {module_name}: {e}")
                continue

            for attr_name, cls in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(cls, ApiInterface)
                    and cls is not ApiInterface
                    and getattr(cls, "PROVIDER_NAME", "")
                ):
                    provider_name = cls.PROVIDER_NAME
                    if provider_name in self._clients:
                        continue  # already registered

                    try:
                        instance = cls()
                        self.register(provider_name, instance)
                    except Exception as e:
                        logger.warning(
                            f"Failed to instantiate {cls.__name__} for provider "
                            f"'{provider_name}': {e} — skipping"
                        )

        logger.info(f"Auto-discovered {len(self._clients)} providers: {self.list_providers()}")
