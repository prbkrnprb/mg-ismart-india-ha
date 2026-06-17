"""Config flow for MG iSmart India."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD

from .client import MgIndiaApiError, MgIndiaClient, hash_control_pin
from .const import CONF_PHONE, CONF_PIN, CONF_PIN_HASH, CONF_VIN, DOMAIN, LOGGER


class MgIndiaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an MG iSmart India config flow."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MgIndiaOptionsFlow:
        return MgIndiaOptionsFlow(config_entry)

    def __init__(self) -> None:
        self._phone: str | None = None
        self._password: str | None = None
        self._vehicles: dict[str, str] = {}
        self._selected_vin: str | None = None

    async def async_step_user(self, user_input=None):
        """Collect phone/password and fetch vehicles."""

        errors: dict[str, str] = {}
        if user_input is not None:
            self._phone = user_input[CONF_PHONE]
            self._password = user_input[CONF_PASSWORD]
            client: MgIndiaClient | None = None
            try:
                client = MgIndiaClient(self._phone, self._password)
                vehicles = await client.vehicles()
            except MgIndiaApiError:
                errors["base"] = "auth"
            except Exception as err:  # noqa: BLE001
                LOGGER.exception("Failed to connect to MG iSmart India: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                if client is not None:
                    await client.close()

            if not errors:
                self._vehicles = {
                    vehicle.vin: vehicle.model_name or vehicle.vin
                    for vehicle in vehicles
                }
                if not self._vehicles:
                    errors["base"] = "no_vehicles"
                elif len(self._vehicles) == 1:
                    self._selected_vin = next(iter(self._vehicles))
                    await self.async_set_unique_id(self._selected_vin)
                    self._abort_if_unique_id_configured()
                    return await self.async_step_control_pin()
                else:
                    return await self.async_step_vehicle()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PHONE): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_vehicle(self, user_input=None):
        """Let the user choose a vehicle when the account has more than one."""

        if user_input is not None:
            self._selected_vin = user_input[CONF_VIN]
            await self.async_set_unique_id(self._selected_vin)
            self._abort_if_unique_id_configured()
            return await self.async_step_control_pin()

        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema({vol.Required(CONF_VIN): vol.In(self._vehicles)}),
            errors={},
        )

    async def async_step_control_pin(self, user_input=None):
        """Verify the vehicle-control PIN before creating the entry."""

        errors: dict[str, str] = {}
        if user_input is not None:
            client: MgIndiaClient | None = None
            try:
                pin_hash = hash_control_pin(user_input[CONF_PIN])
                client = MgIndiaClient(
                    self._phone,
                    self._password,
                    vin=self._selected_vin,
                )
                await client.verify_control_pin(pin_hash)
            except MgIndiaApiError:
                errors["base"] = "invalid_pin"
            except Exception as err:  # noqa: BLE001
                LOGGER.exception("Failed to verify MG control PIN: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                if client is not None:
                    await client.close()
            if not errors:
                return self.async_create_entry(
                    title=self._vehicles[self._selected_vin],
                    data={
                        CONF_PHONE: self._phone,
                        CONF_PASSWORD: self._password,
                        CONF_VIN: self._selected_vin,
                    },
                    options={CONF_PIN_HASH: pin_hash},
                )

        return self.async_show_form(
            step_id="control_pin",
            data_schema=vol.Schema({vol.Required(CONF_PIN): str}),
            errors=errors,
        )


class MgIndiaOptionsFlow(config_entries.OptionsFlow):
    """Configure and verify the vehicle-control PIN."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client: MgIndiaClient | None = None
            try:
                pin_hash = hash_control_pin(user_input[CONF_PIN])
                client = MgIndiaClient(
                    self._config_entry.data[CONF_PHONE],
                    self._config_entry.data[CONF_PASSWORD],
                    vin=self._config_entry.data[CONF_VIN],
                )
                await client.verify_control_pin(pin_hash)
            except MgIndiaApiError:
                errors["base"] = "invalid_pin"
            except Exception as err:  # noqa: BLE001
                LOGGER.exception("Failed to verify MG control PIN: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                if client is not None:
                    await client.close()
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={CONF_PIN_HASH: pin_hash},
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_PIN): str}),
            errors=errors,
        )
