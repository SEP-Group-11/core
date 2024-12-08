"""Calendar platform for a Local Calendar."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

from ical.calendar import Calendar
from ical.event import Event

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_CALENDAR_NAME

PRODID = "-//homeassistant.io//todo 1.0//EN"


# The calendar is populated on creation by converting each todo-item into a calendar event
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the todo calendar platform."""
    calendar = Calendar()
    calendar.prodid = PRODID

    # keys here can also be "shopping_list", etc.
    keys = list(hass.data["google_tasks"].keys())
    asyncConfigEntryAuth = hass.data["google_tasks"][keys[0]]
    list_task_lists = await asyncConfigEntryAuth.list_task_lists()
    list_task = list_task_lists[0]
    tasks = await asyncConfigEntryAuth.list_tasks(list_task["id"])
    print("tasks: ", tasks)

    todo_items: list[any] = []
    todo_events = [_todo_item_to_event(item) for item in todo_items]

    for event in todo_events:
        calendar.events.append(event)

    name = config_entry.data[CONF_CALENDAR_NAME]
    entity = ReadonlyCalendarEntity(calendar, name, unique_id=config_entry.entry_id)
    async_add_entities([entity], True)


class ReadonlyCalendarEntity(CalendarEntity):
    """A calendar entity backed by a todo-list."""

    _attr_has_entity_name = True
    _attr_supported_features = None

    def __init__(
        self,
        calendar: Calendar,
        name: str,
        unique_id: str,
    ) -> None:
        """Initialize LocalCalendarEntity."""
        self._calendar = calendar
        self._calendar_lock = asyncio.Lock()
        self._attr_name = name
        self._attr_unique_id = unique_id

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = self._calendar.timeline_tz(start_date.tzinfo).overlapping(
            start_date,
            end_date,
        )
        # Simply converts each calendar item into a homeassistant CalendarEvent
        return [_get_calendar_event(event) for event in events]


# The same as `components/local_calendar/calendar.py#_get_calendar_event`
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


def _todo_item_to_event(todo_item: TodoItem) -> Event:
    """Convert a todo-item into a calendar event."""

    # start == end time is a really short event
    return Event(
        summary=todo_item.summary,
        start=todo_item.due,
        end=todo_item.due,
        description=todo_item.description,
        uid=todo_item.uid,
        # rrule=event.rrule.as_rrule_str() if event.rrule else None,
        # recurrence_id=event.recurrence_id,
        # location=event.location,
    )
