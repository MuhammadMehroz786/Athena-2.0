import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_session_runs_select_one(session):
    result = await session.execute(text("select 1"))
    assert result.scalar_one() == 1
