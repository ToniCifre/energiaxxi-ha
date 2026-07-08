import logging

from homeassistant import config_entries
import voluptuous as vol

from .api import EnergiaxxiAPI, InvalidCredentialsError, IncapsulaDetectedError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EnergiaxxiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

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
        self._reauth_username = entry_data["username"]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self._validate(self._reauth_username, user_input["password"])
            except InvalidCredentialsError:
                errors["base"] = "invalid_auth"
            except IncapsulaDetectedError:
                errors["base"] = "incapsula"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Energiaxxi credentials")
                errors["base"] = "unknown"
            else:
                entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        "username": self._reauth_username,
                        "password": user_input["password"],
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
        )
