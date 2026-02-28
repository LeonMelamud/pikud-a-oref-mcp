import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

from src.services.sse import alert_event_generator
from src.core.alert_queue import alert_queue

@pytest.mark.asyncio
async def test_alert_event_generator_yields_formatted_alert():
    """
    Tests that the generator takes an alert from the queue, formats it
    correctly as an SSE message, and yields it.
    """
    # Arrange
    mock_request = Mock()
    mock_request.is_disconnected = AsyncMock(return_value=False)
    
    test_alert = {"id": "test1", "data": "This is a test alert"}
    await alert_queue.put(test_alert)

    # Act
    generator = alert_event_generator(mock_request)
    output = await asyncio.wait_for(generator.__anext__(), timeout=1)

    # Assert
    expected_output = 'event: new_alert\ndata: {"id": "test1", "data": "This is a test alert"}\n\n'
    assert output == expected_output

@pytest.mark.asyncio
async def test_alert_event_generator_stops_on_disconnect():
    """
    Tests that the generator exits gracefully if the client disconnects.
    """
    # Arrange
    mock_request = Mock()
    mock_request.is_disconnected = AsyncMock(return_value=True)

    # Act & Assert
    generator = alert_event_generator(mock_request)
    # The generator should stop immediately and not yield anything
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(generator.__anext__(), timeout=1)

@pytest.fixture(autouse=True)
async def clear_queue():
    """
    A fixture to ensure the alert_queue is empty before and after each test.
    This prevents state from leaking between tests.
    """
    # Before test: ensure queue is empty
    while not alert_queue.empty():
        alert_queue.get_nowait()
        
    yield
    
    # After test: ensure queue is empty
    while not alert_queue.empty():
        alert_queue.get_nowait() 