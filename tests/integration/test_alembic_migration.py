import subprocess
import os
import pytest


def test_alembic_upgrade_head_runs_against_postgres():
    if not os.environ.get("RUN_PG_TESTS"):
        pytest.skip("set RUN_PG_TESTS=1 to run (requires docker compose up postgres)")
    result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
