"""Test Mealie diagnostics."""

from unittest.mock import AsyncMock

from syrupy import SnapshotAssertion

from homeassistant.core import HomeAssistant

from . import setup_integration

from tests.common import MockConfigEntry
from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator


async def test_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_mealie_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config entry diagnostics."""
    await setup_integration(hass, mock_config_entry)
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    def normalize_mealplan_id(data):
        """Normalize mealplan_id to string type."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "mealplan_id" and isinstance(value, int):
                    data[key] = str(value)
                else:
                    normalize_mealplan_id(value)
        elif isinstance(data, list):
            for item in data:
                normalize_mealplan_id(item)
        return data

    normalized_diagnostics = normalize_mealplan_id(diagnostics)

    assert normalized_diagnostics == snapshot
