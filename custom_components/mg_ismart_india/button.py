"""One-shot vehicle controls for MG iSmart India."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    if capabilities.find_my_car:
        entities.extend(
            [
                MgIndiaButton(
                    coordinator,
                    data["client"],
                    "find_my_car",
                    "Find My Car",
                    "mdi:car-search",
                    "find",
                ),
                MgIndiaButton(
                    coordinator,
                    data["client"],
                    "stop_find_my_car",
                    "Stop Find My Car",
                    "mdi:car-off",
                    "stop_find",
                ),
            ]
        )
    if capabilities.tailgate:
        entities.append(
            MgIndiaButton(
                coordinator,
                data["client"],
                "release_tailgate",
                "Release Tailgate",
                "mdi:car-back",
                "tailgate",
            )
        )
    async_add_entities(entities)


class MgIndiaButton(MgIndiaEntity, ButtonEntity):
    def __init__(
        self,
        coordinator,
        client: MgIndiaClient,
        key: str,
        name: str,
        icon: str,
        action: str,
    ) -> None:
        super().__init__(coordinator, key, name)
        self._client = client
        self._attr_icon = icon
        self._action = action

    @property
    def available(self) -> bool:
        return super().available and self._client.has_control_pin

    async def async_press(self) -> None:
        if self._action == "find":
            await self._client.find_my_car()
        elif self._action == "stop_find":
            await self._client.find_my_car(stop=True)
        else:
            await self._client.release_tailgate()
        await self.coordinator.async_request_refresh()
