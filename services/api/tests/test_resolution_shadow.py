import asyncio

import pytest

from app.resolution.shadow import run_shadow


@pytest.mark.asyncio
async def test_returns_primary_and_emits_redacted_shadow_success():
    events = []

    async def primary():
        return {"answer": "primary", "action": "queue"}

    async def shadow():
        return "raw shadow output"

    result = await run_shadow(primary, shadow, enabled=True, callback=events.append,
                              metadata={"tenant": "tenant-a", "question": "raw question"})
    assert result["answer"] == "primary"
    assert events[0]["outcome"] == "success"
    assert "question" not in events[0]
    assert "raw shadow output" not in str(events)


@pytest.mark.asyncio
async def test_shadow_failure_and_timeout_are_fail_open():
    events = []

    async def primary():
        return "primary"

    async def failing_shadow():
        raise RuntimeError("private model output")

    assert await run_shadow(primary, failing_shadow, enabled=True, callback=events.append) == "primary"
    assert events[-1]["outcome"] == "failure"

    async def slow_shadow():
        await asyncio.sleep(1)

    assert await run_shadow(primary, slow_shadow, enabled=True, callback=events.append,
                            timeout_seconds=0.001) == "primary"
    assert events[-1]["outcome"] == "timeout"


@pytest.mark.asyncio
async def test_kill_switch_does_not_start_shadow():
    called = False

    async def primary():
        return 7

    async def shadow():
        nonlocal called
        called = True

    assert await run_shadow(primary, shadow, enabled=False) == 7
    assert called is False
