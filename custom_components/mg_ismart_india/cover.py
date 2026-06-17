"""Window and sunroof controls for MG iSmart India."""

from __future__ import annotations

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import discover_capabilities
from .client import MgIndiaClient
from .const import DOMAIN
from .entity import MgIndiaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    capabilities = discover_capabilities(
        coordinator.data.vehicle.raw, coordinator.data.features
    )
    entities = []
    if capabilities.window_param_ids:
        entities.append(MgIndiaWindows(coordinator, data["client"]))
    if capabilities.sunroof:
        entities.append(MgIndiaSunroof(coordinator, data["client"]))
    async_add_entities(entities)


class _MgIndiaCover(MgIndiaEntity, CoverEntity):
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, coordinator, key: str, name: str, client: MgIndiaClient) -> None:
        super().__init__(coordinator, key, name)
        self._client = client

    @property
    def available(self) -> bool:
        return super().available and self._client.has_control_pin


class MgIndiaWindows(_MgIndiaCover):
    _attr_device_class = CoverDeviceClass.WINDOW

    def __init__(self, coordinator, client: MgIndiaClient) -> None:
        super().__init__(coordinator, "windows_control", "Windows", client)

    @property
    def is_closed(self) -> bool | None:
        status = self.coordinator.data.status
        if status is None:
            return None
        capabilities = discover_capabilities(
            self.coordinator.data.vehicle.raw, self.coordinator.data.features
        )
        values = {
            9: status.driver_window_open,
            10: status.passenger_window_open,
            11: status.rear_left_window_open,
            12: status.rear_right_window_open,
        }
        observed = [
            values[item]
            for item in capabilities.window_param_ids
            if values[item] is not None
        ]
        return not any(observed) if observed else None

    async def async_open_cover(self, **kwargs) -> None:
        capabilities = discover_capabilities(
            self.coordinator.data.vehicle.raw, self.coordinator.data.features
        )
        await self._client.control_windows(
            open_windows=True, window_param_ids=capabilities.window_param_ids
        )
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs) -> None:
        capabilities = discover_capabilities(
            self.coordinator.data.vehicle.raw, self.coordinator.data.features
        )
        await self._client.control_windows(
            open_windows=False, window_param_ids=capabilities.window_param_ids
        )
        await self.coordinator.async_request_refresh()


class MgIndiaSunroof(_MgIndiaCover):
    _attr_device_class = CoverDeviceClass.DAMPER

    def __init__(self, coordinator, client: MgIndiaClient) -> None:
        super().__init__(coordinator, "sunroof_control", "Sunroof", client)

    @property
    def is_closed(self) -> bool | None:
        status = self.coordinator.data.status
        return (
            not status.sunroof_open
            if status and status.sunroof_open is not None
            else None
        )

    async def async_open_cover(self, **kwargs) -> None:
        await self._client.control_sunroof(open_sunroof=True)
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs) -> None:
        await self._client.control_sunroof(open_sunroof=False)
        await self.coordinator.async_request_refresh()
