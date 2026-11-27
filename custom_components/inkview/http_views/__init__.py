"""HTTP views exposed by the InkView integration."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from ..const import URL_PREFIX
from .auth import InkViewAuthTokenView
from .energy import InkViewEnergyTotalsView
from .health import InkViewHealthView
from .states import InkViewStateView
from .states_batch import InkViewBatchStateView
from .states_list import InkViewStatesListView


async def register_views(hass: HomeAssistant) -> None:
    """Register views and static paths; caller must invoke this once per HA instance."""
    hass.http.register_view(InkViewAuthTokenView())
    hass.http.register_view(InkViewStatesListView())
    hass.http.register_view(InkViewStateView())
    hass.http.register_view(InkViewBatchStateView())
    hass.http.register_view(InkViewEnergyTotalsView())
    hass.http.register_view(InkViewHealthView())

    public_root = Path(__file__).resolve().parent.parent / "public"
    static_paths: list[StaticPathConfig] = []
    logo_dir = public_root / "logo"
    if logo_dir.is_dir():
        static_paths.append(
            StaticPathConfig(f"{URL_PREFIX}/static", str(logo_dir), False)
        )
    panel_dir = public_root / "panel"
    if panel_dir.is_dir():
        # Cacheable: panel.py fingerprints the URL with ?v=<VERSION>.
        static_paths.append(
            StaticPathConfig(f"{URL_PREFIX}/panel", str(panel_dir), True)
        )
    if static_paths:
        await hass.http.async_register_static_paths(static_paths)


__all__ = [
    "register_views",
    "InkViewAuthTokenView",
    "InkViewStatesListView",
    "InkViewStateView",
    "InkViewBatchStateView",
    "InkViewEnergyTotalsView",
    "InkViewHealthView",
]
