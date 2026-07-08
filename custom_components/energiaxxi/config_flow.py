import logging

from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

from .api import EnergiaxxiAPI, InvalidCredentialsError, IncapsulaDetectedError
from .const import (
    CONF_HISTORY_DAYS,
    CONF_PRICE_DAYS,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_PRICE_DAYS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class EnergiaxxiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EnergiaxxiOptionsFlow()

    async def _validate(self, username: str, password: str) -> None:
        """Validate credentials against the API. Raises on failure."""
        api = EnergiaxxiAPI(username, password)
        await self.hass.async_add_executor_job(api.authenticate)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self._validate(user_input["username"], user_input["password"])
            except InvalidCredentialsError:
                errors["base"] = "invalid_auth"
            except IncapsulaDetectedError:
                errors["base"] = "incapsula"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Energiaxxi credentials")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input["username"].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input["username"],
                    data={
                        "username": user_input["username"],
                        "password": user_input["password"],
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required("username"): str,
                vol.Required("password"): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        reauth_entry = self._get_reauth_entry()
        username = reauth_entry.data["username"]
        if user_input is not None:
            try:
                await self._validate(username, user_input["password"])
            except InvalidCredentialsError:
                errors["base"] = "invalid_auth"
            except IncapsulaDetectedError:
                errors["base"] = "incapsula"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Energiaxxi credentials")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={"username": username, "password": user_input["password"]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            description_placeholders={"username": username},
            errors=errors,
        )


class EnergiaxxiOptionsFlow(config_entries.OptionsFlow):

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HISTORY_DAYS,
                    default=options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                ): vol.All(int, vol.Range(min=1, max=60)),
                vol.Required(
                    CONF_PRICE_DAYS,
                    default=options.get(CONF_PRICE_DAYS, DEFAULT_PRICE_DAYS),
                ): vol.All(int, vol.Range(min=1, max=60)),
                vol.Required(
                    CONF_SCAN_INTERVAL_HOURS,
                    default=options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS),
                ): vol.All(int, vol.Range(min=1, max=48)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
