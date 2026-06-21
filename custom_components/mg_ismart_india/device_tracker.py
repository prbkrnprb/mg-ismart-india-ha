"""Device tracker for MG iSmart India."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

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


class MgIndiaDeviceTracker(MgIndiaEntity, TrackerEntity, RestoreEntity):
    """MG iSmart India GPS device tracker."""

    def __init__(self, coordinator: MgIndiaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "location", "Location")
        self._last_latitude: float | None = None
        self._last_longitude: float | None = None
        self._last_altitude: int | None = None
        self._last_heading: int | None = None
        self._last_speed: float | None = None
        self._last_gps_fix: str | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last known position on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.attributes:
            self._last_latitude = last_state.attributes.get("latitude")
            self._last_longitude = last_state.attributes.get("longitude")
            self._last_altitude = last_state.attributes.get("altitude")
            self._last_heading = last_state.attributes.get("heading")
            self._last_speed = last_state.attributes.get("speed")
            self._last_gps_fix = last_state.attributes.get("gps_fix")
        self._update_from_coordinator()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    def _update_from_coordinator(self) -> None:
        """Cache latest GPS data from coordinator."""
        if self.coordinator.data.status and self.coordinator.data.status.gps:
            gps = self.coordinator.data.status.gps
            if gps.latitude is not None and gps.longitude is not None:
                self._last_latitude = gps.latitude
                self._last_longitude = gps.longitude
                self._last_altitude = gps.altitude
                self._last_heading = gps.heading
                self._last_speed = gps.speed
                self._last_gps_fix = gps.gps_fix

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self._last_latitude

    @property
    def longitude(self) -> float | None:
        return self._last_longitude

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        attrs = {}
        if self._last_altitude is not None:
            attrs["altitude"] = self._last_altitude
        if self._last_heading is not None:
            attrs["heading"] = self._last_heading
        if self._last_speed is not None:
            attrs["speed"] = self._last_speed
        if self._last_gps_fix is not None:
            attrs["gps_fix"] = self._last_gps_fix
        return attrs if attrs else None
