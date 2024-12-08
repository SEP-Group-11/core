"""Calendar platform for a Local Calendar."""

from homeassistant.components.todo.calendar import (
    async_setup_entry as super_async_setup_entry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


# The calendar is populated on creation by converting each todo-item into a calendar event
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the todo calendar platform."""
    await super_async_setup_entry(hass, config_entry, async_add_entities)
