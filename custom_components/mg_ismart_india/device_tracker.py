"""Device tracker for MG iSmart India."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MgIndiaDataUpdateCoordinator
from .entity import MgIndiaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up MG iSmart India device tracker."""

    coordinator: MgIndiaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([MgIndiaDeviceTracker(coordinator)])


class MgIndiaDeviceTracker(MgIndiaEntity, TrackerEntity):
    """MG iSmart India GPS device tracker."""

    def __init__(self, coordinator: MgIndiaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "location", "Location")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        if self.coordinator.data.status and self.coordinator.data.status.gps:
            return self.coordinator.data.status.gps.latitude
        return None

    @property
    def longitude(self) -> float | None:
        if self.coordinator.data.status and self.coordinator.data.status.gps:
            return self.coordinator.data.status.gps.longitude
        return None

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        if not self.coordinator.data.status or not self.coordinator.data.status.gps:
            return None
        gps = self.coordinator.data.status.gps
        attrs = {}
        if gps.altitude is not None:
            attrs["altitude"] = gps.altitude
        if gps.heading is not None:
            attrs["heading"] = gps.heading
        if gps.speed is not None:
            attrs["speed"] = gps.speed
        if gps.gps_fix is not None:
            attrs["gps_fix"] = gps.gps_fix
        return attrs if attrs else None
