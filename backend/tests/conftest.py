import asyncio
import pytest

@pytest.fixture(autouse=True)
def isolate_worker(monkeypatch):
    async def idle(factory):
        await asyncio.Future()
    monkeypatch.setattr("backend.operations.worker",idle)

@pytest.fixture(autouse=True)
def python39_event_loop():
    # asyncio.run clears the thread's current loop on Python 3.9.
    loop=asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    loop.close()
    asyncio.set_event_loop(None)

@pytest.fixture(autouse=True)
def authenticated_unit_operator(monkeypatch):
    monkeypatch.setattr("backend.auth.session_user",lambda token:{"username":"testadmin","role":"Admin"})
