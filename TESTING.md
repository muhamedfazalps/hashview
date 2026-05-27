# Testing

This document describes the local and CI testing setup for Hashview, including how to run tests against the dev Docker containers.

## Local prerequisites

- Python virtual environment in `.venv`
- Docker + Docker Compose
- Playwright browsers installed (`python -m playwright install`)

## Environment files

Tests load `.env.test` via `tests/conftest.py`. At minimum, set:

```
HASHVIEW_E2E_BASE_URL=http://127.0.0.1:5000
HASHVIEW_E2E_EMAIL=admin@example.com
HASHVIEW_E2E_PASSWORD=your_password
HASHVIEW_E2E_API_KEY=your_api_key
HASHVIEW_E2E_TASK_ID=1
HASHVIEW_E2E_JOB_ID=1
HASHVIEW_E2E_CUSTOMER_ID=1
HASHVIEW_E2E_HASHFILE_ID=1
HASHVIEW_E2E_TASK_NAME=Rockyou Wordlist
```

Optional:

```
HASHVIEW_E2E_CUSTOMER_NAME=E2E Customer
HASHVIEW_E2E_SETUP_EMAIL=admin@example.com
HASHVIEW_E2E_SETUP_PASSWORD=your_password
HASHVIEW_E2E_ENFORCE_OPEN_REDIRECT=1
```

## Running tests locally (live host)

Run the app and DB with Docker Compose, then execute pytest:

```
docker compose up -d
set -a; source .env.test; set +a
./.venv/bin/python -m pytest -m e2e -vv -s --maxfail=1
```

### Using the helper script

```
./tests/run_e2e_compose.sh
```

This script:
- Starts containers (`docker compose up -d --build`)
- Waits for the app at `HASHVIEW_E2E_BASE_URL`
- Runs E2E tests
- Prints Docker logs on failure

## Test suites

- **E2E**: `pytest -m e2e`
  - Uses Playwright against a live host.
  - `tests/e2e/test_agent_sim.py` runs a heartbeat-only agent simulation (no DB dependency).
  - Some tests are optional and may skip if credentials or IDs are missing.

- **Security**: `pytest -m security`
  - Includes command-injection regression tests in `tests/security/`.

## CI / CD (dev Docker containers)

Recommended CI flow:

1) Build and start dev containers:

```
docker compose up -d --build
```

2) Run E2E:

```
set -a; source .env.test; set +a
./.venv/bin/python -m pytest -m e2e -vv -s --maxfail=1
```

3) Optionally run security tests:

```
./.venv/bin/python -m pytest -m security -vv
```

4) Tear down:

```
docker compose down -v
```

## Notes

- The open-redirect test is `xfail` by default. Set `HASHVIEW_E2E_ENFORCE_OPEN_REDIRECT=1` to make it a hard failure.
- The agent simulator test does not require database access; it validates heartbeat registration only.
- If Playwright browsers are missing in CI, install them once:

```
./.venv/bin/python -m playwright install
```
