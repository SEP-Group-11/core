"""Calendar platform for a Local Calendar."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from ical.event import Event
from ical.calendar import Calendar
from ical.types import Range, Recur
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.components.calendar.const import (
    EVENT_END,
    EVENT_RRULE,
    EVENT_START,
    CalendarEntityFeature,
)
from homeassistant.components.todo import TodoListEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import _LOGGER, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from ical.store import EventStore, EventStoreError
from homeassistant.const import CONF_ENTITY_ID, EVENT_COMPONENT_LOADED
from homeassistant.helpers import entity_registry as er

PRODID = "-//homeassistant.io//google_tasks 1.0//EN"


# The calendar is populated on creation by converting each todo-item into a calendar event
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the todo calendar platform."""

    keys = list(hass.data["google_tasks"].keys())
    asyncConfigEntryAuth = hass.data["google_tasks"][keys[0]]
    list_task_lists = await asyncConfigEntryAuth.list_task_lists()
    for list_task in list_task_lists:
        calendar = Calendar()
        calendar.prodid = PRODID
        tasks = await asyncConfigEntryAuth.list_tasks(list_task["id"])
        filtered_tasks = [task for task in tasks if "due" in task]
        todo_events = [_todo_item_to_event(item) for item in filtered_tasks]
        for event in todo_events:
            calendar.events.append(event)

        calendar_entity = InMemoryCalendarEntity(
            calendar, list_task["title"], config_entry.entry_id, list_task["id"]
        )
        async_add_entities([calendar_entity], True)

        async def _handle_component_loaded(event):
            component = event.data.get("component")
            if component == "google_tasks":
                # second-phase setup
                entity_reg = er.async_get(hass)
                entries = er.async_entries_for_config_entry(
                    entity_reg, config_entry.entry_id
                )
                todo_component = hass.data["todo"]
                entities = [
                    todo_component.get_entity(entry.entity_id) for entry in entries
                ]
                entities = [
                    entity
                    for entity in entities
                    if entity is not None and isinstance(entity, TodoListEntity)
                ]
                for entity in entities:
                    entity.async_subscribe_updates(
                        lambda item_list: _handle_todo_events(
                            calendar_entity, item_list
                        )
                    )

        hass.bus.async_listen(EVENT_COMPONENT_LOADED, _handle_component_loaded)


def _handle_todo_events(entity: InMemoryCalendarEntity, item_list):
    entity.clear_calendar()
    if item_list:
        for item in item_list:
            if item["due"] is not None:
                event = _item_list_item_to_event(item)
                entity.append_calendar(event)


class InMemoryCalendarEntity(CalendarEntity):
    """A calendar entity backed by memory."""

    _attr_has_entity_name = True
    _attr_supported_features = ()

    def __init__(
        self,
        calendar: Calendar,
        name: str,
        config_entry_id: str,
        task_list_id: str,
    ) -> None:
        """Initialize LocalCalendarEntity."""
        self._calendar = calendar
        self._calendar_lock = asyncio.Lock()
        self._event: CalendarEvent | None = None
        self._attr_name = name
        self._attr_unique_id = f"{config_entry_id}-{task_list_id}"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        return self._event

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Get all events in a specific time frame."""
        events = self._calendar.timeline_tz(start_date.tzinfo).overlapping(
            start_date,
            end_date,
        )
        return [_get_calendar_event(event) for event in events]

    async def async_update(self) -> None:
        """Update entity state with the next upcoming event."""
        now = dt_util.now()
        events = self._calendar.timeline_tz(now.tzinfo).active_after(now)
        if event := next(events, None):
            self._event = _get_calendar_event(event)
        else:
            self._event = None

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add a new event to calendar."""
        event = _parse_event(kwargs)
        async with self._calendar_lock:
            event_store = EventStore(self._calendar)
            await self.hass.async_add_executor_job(event_store.add, event)
        await self.async_update_ha_state(force_refresh=True)

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Delete an event on the calendar."""
        range_value: Range = Range.NONE
        if recurrence_range == Range.THIS_AND_FUTURE:
            range_value = Range.THIS_AND_FUTURE
        async with self._calendar_lock:
            try:
                EventStore(self._calendar).delete(
                    uid,
                    recurrence_id=recurrence_id,
                    recurrence_range=range_value,
                )
            except EventStoreError as err:
                raise HomeAssistantError(f"Error while deleting event: {err}") from err
            await self._async_store()
        await self.async_update_ha_state(force_refresh=True)

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Update an existing event on the calendar."""
        await self.async_update_ha_state(force_refresh=True)

    def clear_calendar(self):
        self._calendar.events.clear()

    def append_calendar(self, event: Event):
        self._calendar.events.append(event)


def _get_calendar_event(event: Event) -> CalendarEvent:
    """Return a CalendarEvent from an API event."""
    start: datetime | date
    end: datetime | date
    if isinstance(event.start, datetime) and isinstance(event.end, datetime):
        start = dt_util.as_local(event.start)
        end = dt_util.as_local(event.end)
        if (end - start) <= timedelta(seconds=0):
            end = start + timedelta(minutes=30)
    else:
        start = event.start
        end = event.end
        if (end - start) < timedelta(days=0):
            end = start + timedelta(days=1)

    return CalendarEvent(
        summary=event.summary,
        start=start,
        end=end,
        description=event.description,
        uid=event.uid,
        rrule=event.rrule.as_rrule_str() if event.rrule else None,
        recurrence_id=event.recurrence_id,
        location=event.location,
    )


def _todo_item_to_event(todo_item: dict) -> Event:
    """Convert a todo-item into a calendar event."""
    # start == end time is a really short event
    return Event(
        summary=todo_item["title"],
        start=todo_item["due"],
        end=todo_item["due"],
        # description=todo_item["description"],
        uid=todo_item["id"],
        # rrule=event.rrule.as_rrule_str() if event.rrule else None,
        # recurrence_id=event.recurrence_id,
        # location=event.location,
    )


def _item_list_item_to_event(item: dict) -> Event:
    return Event(
        summary=item["summary"],
        start=item["due"],
        end=item["due"],
        # description=todo_item["description"],
        uid=item["uid"],
        # rrule=event.rrule.as_rrule_str() if event.rrule else None,
        # recurrence_id=event.recurrence_id,
        # location=event.location,
    )


def _parse_event(event: dict[str, Any]) -> Event:
    """Parse an ical event from a home assistant event dictionary."""
    # if rrule := event.get(EVENT_RRULE):
    #     event[EVENT_RRULE] = Recur.from_rrule(rrule)

    # This function is called with new events created in the local timezone,
    # however ical library does not properly return recurrence_ids for
    # start dates with a timezone. For now, ensure any datetime is stored as a
    # floating local time to ensure we still apply proper local timezone rules.
    # This can be removed when ical is updated with a new recurrence_id format
    # https://github.com/home-assistant/core/issues/87759
    for key in (EVENT_START, EVENT_END):
        if (
            (value := event[key])
            and isinstance(value, datetime)
            and value.tzinfo is not None
        ):
            event[key] = dt_util.as_local(value).replace(tzinfo=None)

    try:
        return Event(**event)
    except Exception as err:
        _LOGGER.debug("Error parsing event input fields: %s (%s)", event, str(err))
        raise vol.Invalid("Error parsing event input fields") from err
