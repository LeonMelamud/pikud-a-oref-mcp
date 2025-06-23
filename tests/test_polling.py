import asyncio
import pytest
import respx
from httpx import Response
from unittest.mock import AsyncMock, patch
from polling import poll_for_alerts, POHA_API_URL, POHA_HISTORY_API_URL, get_alert_type_by_category

# Helper to create a mock alert
def create_mock_alert(alert_id, cat, data, title):
    return {"id": alert_id, "cat": cat, "data": data, "title": title}

@pytest.mark.asyncio
@respx.mock
async def test_poll_for_alerts_new_alert_found_on_primary():
    """
    Tests that a new alert from the primary API is structured correctly and queued.
    """
    mock_alert = create_mock_alert("12345", 1, ["Tel Aviv"], "Enter Shelters")
    respx.get(POHA_API_URL).mock(return_value=Response(200, json=mock_alert))
    respx.get(POHA_HISTORY_API_URL).mock(return_value=Response(200, text=""))

    with patch('polling.app_state') as mock_state, patch('polling.alert_queue') as mock_queue:
        mock_state.last_alert_id = None
        mock_queue.put = AsyncMock()

        polling_task = asyncio.create_task(poll_for_alerts())
        await asyncio.sleep(0.1)

        assert mock_state.last_alert_id == "12345"
        expected_alert = {
            "id": "12345",
            "type": "missiles",
            "cities": ["Tel Aviv"],
            "instructions": "Enter Shelters"
        }
        mock_queue.put.assert_called_with(expected_alert)

        polling_task.cancel()
        await asyncio.gather(polling_task, return_exceptions=True)

@pytest.mark.asyncio
@respx.mock
async def test_poll_for_alerts_fallback_to_history_api():
    """
    Tests that the poller falls back to the history API when the primary is empty.
    """
    mock_alert = create_mock_alert("67890", 5, ["Haifa"], "Hostile Aircraft")
    respx.get(POHA_API_URL).mock(return_value=Response(200, text=""))
    respx.get(POHA_HISTORY_API_URL).mock(return_value=Response(200, json=[mock_alert]))

    with patch('polling.app_state') as mock_state, patch('polling.alert_queue') as mock_queue:
        mock_state.last_alert_id = None
        mock_queue.put = AsyncMock()

        polling_task = asyncio.create_task(poll_for_alerts())
        await asyncio.sleep(0.1)

        assert mock_state.last_alert_id == "67890"
        expected_alert = {
            "id": "67890",
            "type": "hostileAircraftIntrusion",
            "cities": ["Haifa"],
            "instructions": "Hostile Aircraft"
        }
        mock_queue.put.assert_called_with(expected_alert)

        polling_task.cancel()
        await asyncio.gather(polling_task, return_exceptions=True)


@pytest.mark.asyncio
@respx.mock
async def test_poll_for_alerts_no_new_alert():
    """
    Tests that if the poller sees the same alert ID again, it does not queue a duplicate.
    """
    mock_alert = create_mock_alert("12345", 1, ["Tel Aviv"], "Enter Shelters")
    respx.get(POHA_API_URL).mock(return_value=Response(200, json=mock_alert))
    respx.get(POHA_HISTORY_API_URL).mock(return_value=Response(200, text=""))

    with patch('polling.app_state') as mock_state, patch('polling.alert_queue') as mock_queue:
        mock_state.last_alert_id = "12345"
        mock_queue.put = AsyncMock()

        polling_task = asyncio.create_task(poll_for_alerts())
        await asyncio.sleep(0.1)

        mock_queue.put.assert_not_called()

        polling_task.cancel()
        await asyncio.gather(polling_task, return_exceptions=True)


@pytest.mark.asyncio
@respx.mock
async def test_poll_for_alerts_filters_test_alerts():
    """
    Tests that alerts containing the test keyword are ignored.
    """
    mock_alert = create_mock_alert("55555", 1, ["Test City בדיקה"], "Test")
    respx.get(POHA_API_URL).mock(return_value=Response(200, json=mock_alert))
    respx.get(POHA_HISTORY_API_URL).mock(return_value=Response(200, text=""))

    with patch('polling.app_state') as mock_state, patch('polling.alert_queue') as mock_queue:
        mock_state.last_alert_id = None
        mock_queue.put = AsyncMock()

        polling_task = asyncio.create_task(poll_for_alerts())
        await asyncio.sleep(0.1)

        mock_queue.put.assert_not_called()
        assert mock_state.last_alert_id is None

        polling_task.cancel()
        await asyncio.gather(polling_task, return_exceptions=True)


@pytest.mark.asyncio
@respx.mock
async def test_poll_for_alerts_handles_api_errors_gracefully():
    """
    Tests that the poller handles HTTP errors from both APIs without crashing.
    """
    respx.get(POHA_API_URL).mock(return_value=Response(500))
    respx.get(POHA_HISTORY_API_URL).mock(return_value=Response(500))

    with patch('polling.alert_queue') as mock_queue:
        mock_queue.put = AsyncMock()

        polling_task = asyncio.create_task(poll_for_alerts())
        await asyncio.sleep(0.1)

        mock_queue.put.assert_not_called()

        polling_task.cancel()
        await asyncio.gather(polling_task, return_exceptions=True)

def test_get_alert_type_by_category():
    """
    Tests the mapping of category IDs to alert type strings.
    """
    assert get_alert_type_by_category(1) == "missiles"
    assert get_alert_type_by_category(5) == "hostileAircraftIntrusion"
    assert get_alert_type_by_category(20) == "newsFlash"
    assert get_alert_type_by_category(999) == "unknown" # Test fallback