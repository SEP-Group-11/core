"""Support for Alexa skill service end point."""

import hmac
from http import HTTPStatus
import logging
import uuid

from aiohttp.web_response import StreamResponse

from homeassistant.components import http
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import template
from homeassistant.helpers.typing import ConfigType
import homeassistant.util.dt as dt_util

from .const import (
    API_PASSWORD,
    ATTR_MAIN_TEXT,
    ATTR_REDIRECTION_URL,
    ATTR_STREAM_URL,
    ATTR_TITLE_TEXT,
    ATTR_UID,
    ATTR_UPDATE_DATE,
    CONF_AUDIO,
    CONF_DISPLAY_URL,
    CONF_TEXT,
    CONF_TITLE,
    CONF_UID,
    DATE_FORMAT,
)

_LOGGER = logging.getLogger(__name__)

FLASH_BRIEFINGS_API_ENDPOINT = "/api/alexa/flash_briefings/{briefing_id}"


@callback
def async_setup(hass: HomeAssistant, flash_briefing_config: ConfigType) -> None:
    """Activate Alexa component."""
    hass.http.register_view(AlexaFlashBriefingView(hass, flash_briefing_config))


class AlexaFlashBriefingView(http.HomeAssistantView):
    """Handle Alexa Flash Briefing skill requests."""

    url = FLASH_BRIEFINGS_API_ENDPOINT
    requires_auth = False
    name = "api:alexa:flash_briefings"

    def __init__(self, hass: HomeAssistant, flash_briefings: ConfigType) -> None:
        """Initialize Alexa view."""
        super().__init__()
        self.flash_briefings = flash_briefings

    @callback
    def get(
        self, request: http.HomeAssistantRequest, briefing_id: str
    ) -> StreamResponse | tuple[bytes, HTTPStatus]:
        """Handle Alexa Flash Briefing request."""
        _LOGGER.debug("Received Alexa flash briefing request for: %s", briefing_id)

        if not self._authenticate(request, briefing_id):
            return b"", HTTPStatus.UNAUTHORIZED

        briefing_config = self.flash_briefings.get(briefing_id)
        if not isinstance(briefing_config, list):
            _LOGGER.error(
                "No configured Alexa flash briefing was found for: %s", briefing_id
            )
            return b"", HTTPStatus.NOT_FOUND

        briefing = self._generate_briefing(briefing_config)
        return self.json(briefing)

    def _authenticate(
        self, request: http.HomeAssistantRequest, briefing_id: str
    ) -> bool:
        if request.query.get(API_PASSWORD) is None:
            _LOGGER.error(
                "No password provided for Alexa flash briefing: %s", briefing_id
            )
            return False

        if not hmac.compare_digest(
            request.query[API_PASSWORD].encode("utf-8"),
            self.flash_briefings[CONF_PASSWORD].encode("utf-8"),
        ):
            _LOGGER.error("Wrong password for Alexa flash briefing: %s", briefing_id)
            return False

        return True

    def _generate_briefing(self, briefing_config: list) -> list:
        briefing = []
        for item in briefing_config:
            output = self._process_briefing_item(item)
            briefing.append(output)
        return briefing

    def _process_briefing_item(self, item: dict) -> dict:
        output: dict[str, str] = {}
        self._add_text_field(output, item, CONF_TITLE, ATTR_TITLE_TEXT)
        self._add_text_field(output, item, CONF_TEXT, ATTR_MAIN_TEXT)
        self._add_uid(output, item)
        self._add_text_field(output, item, CONF_AUDIO, ATTR_STREAM_URL)
        self._add_text_field(output, item, CONF_DISPLAY_URL, ATTR_REDIRECTION_URL)
        output[ATTR_UPDATE_DATE] = dt_util.utcnow().strftime(DATE_FORMAT)
        return output

    def _add_text_field(
        self, output: dict, item: dict, conf_key: str, attr_key: str
    ) -> None:
        """Add a text field to the output."""
        if item.get(conf_key) is not None:
            if isinstance(item.get(conf_key), template.Template):
                output[attr_key] = item[conf_key].async_render(parse_result=False)
            else:
                output[attr_key] = item.get(conf_key)

    def _add_uid(self, output: dict, item: dict) -> None:
        """Add a unique identifier to the output."""
        uid = item.get(CONF_UID)
        if uid is None:
            uid = str(uuid.uuid4())
        output[ATTR_UID] = uid
