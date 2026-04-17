# Athena 2.0

Monitoring + remediation brain for UniFi/Meraki/Domotz.

## Dev setup
1. `cp .env.example .env`
2. `docker compose up -d postgres redis`
3. `pip install -e .[dev]`
4. `alembic upgrade head`
5. `pytest`
6. `uvicorn athena.api.main:app --reload` (available after Plan 1 Task 12)
