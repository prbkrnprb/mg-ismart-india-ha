"""Heated-seat controls for MG iSmart India."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import discover_capabilities
from .client import MgIndiaClient
from .const import DOMAIN
from .entity import MgIndiaEntity

LEVELS = {"Off": 0, "Low": 1, "Medium": 2, "High": 3}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    capabilities = discover_capabilities(
        coordinator.data.vehicle.raw, coordinator.data.features
    )
    if capabilities.heated_seats:
        async_add_entities(
            [
                MgIndiaHeatedSeat(coordinator, data["client"], "driver"),
                MgIndiaHeatedSeat(coordinator, data["client"], "passenger"),
            ]
        )


class MgIndiaHeatedSeat(MgIndiaEntity, SelectEntity):
    """Control one front heated seat while preserving the other setting."""

    _attr_options = list(LEVELS)
    _attr_icon = "mdi:car-seat-heater"

    def __init__(self, coordinator, client: MgIndiaClient, side: str) -> None:
        super().__init__(
            coordinator, f"{side}_heated_seat", f"{side.title()} Heated Seat"
        )
        self._client = client
        self._side = side

    @property
    def available(self) -> bool:
        capabilities = discover_capabilities(
            self.coordinator.data.vehicle.raw, self.coordinator.data.features
        )
        return (
            super().available
            and self._client.has_control_pin
            and capabilities.heated_seats
        )

    @property
    def current_option(self) -> str:
        level = self._client.heated_seat_level(self._side)
        return next(name for name, value in LEVELS.items() if value == level)

    async def async_select_option(self, option: str) -> None:
        driver = self._client.heated_seat_level("driver")
        passenger = self._client.heated_seat_level("passenger")
        if self._side == "driver":
            driver = LEVELS[option]
        else:
            passenger = LEVELS[option]
        await self._client.control_heated_seats(
            driver_level=driver, passenger_level=passenger
        )
        self.async_write_ha_state()
