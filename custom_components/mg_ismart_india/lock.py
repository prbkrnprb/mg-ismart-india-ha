"""Vehicle lock control for MG iSmart India."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
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
    if capabilities.door_lock:
        async_add_entities([MgIndiaDoorLock(coordinator, data["client"])])


class MgIndiaDoorLock(MgIndiaEntity, LockEntity):
    """Lock or unlock the vehicle doors."""

    def __init__(self, coordinator, client: MgIndiaClient) -> None:
        super().__init__(coordinator, "door_lock_control", "Door Lock")
        self._client = client

    @property
    def available(self) -> bool:
        capabilities = discover_capabilities(
            self.coordinator.data.vehicle.raw, self.coordinator.data.features
        )
        return (
            super().available
            and self._client.has_control_pin
            and capabilities.door_lock
        )

    @property
    def is_locked(self) -> bool | None:
        status = self.coordinator.data.status
        return status.locked if status is not None else None

    async def async_lock(self, **kwargs) -> None:
        await self._client.control_door_lock(lock=True)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs) -> None:
        await self._client.control_door_lock(lock=False)
        await self.coordinator.async_request_refresh()
