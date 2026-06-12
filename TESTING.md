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
  - The dev venv only needs `requirements-dev.txt` (pytest + playwright);
    the app under test lives in docker so the runner doesn't import any
    `hashview.*` modules.
  - `tests/run_e2e_compose.sh` passes `--ignore=tests/security
    --ignore=tests/unit` so pytest doesn't try to import those dirs'
    conftests (which pull in Flask & friends).

- **Security / unit**: `pytest -m security`
  - Includes command-injection regression tests in `tests/security/` and
    the broader unit suite under `tests/unit/` (auth-required sweep, hash
    parsers, dynamic-wordlist dispatcher, migration smoke, API endpoints,
    password reset, hashfile cascade, lucky + one-and-done, etc.).
  - These tests import from the `hashview.*` package, so they need the
    app's runtime dependencies installed too:
    ```
    ./.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
    ./.venv/bin/python -m pytest -m security -vv
    ```
  - The `tests/unit/conftest.py` is guarded with a `collect_ignore_glob`
    that skips the directory if Flask isn't importable, so a stray
    `pytest tests/` against an e2e-only venv won't error at collection.

## Function coverage gate

Every function in `hashview/` must have a unit test that executes it. Verify
locally:

```
./.venv/bin/python -m pytest tests/unit -q --cov=hashview --cov-report=json:coverage.json
./.venv/bin/python tests/check_function_coverage.py
```

The checker parses `coverage.json`, walks every `hashview/*.py` with `ast`, and
exits non-zero listing any function with zero executed body lines (migrations
excluded). Waivers (discouraged) go one-per-line in
`tests/function_coverage_allowlist.txt` as `hashview/path/file.py::function_name`.
`pytest-cov` is required (`./.venv/bin/pip install pytest-cov`).

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
