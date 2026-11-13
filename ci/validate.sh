#!/usr/bin/env bash
set -euo pipefail
: "${TEST_DATABASE_URL:?Use an owned disposable PostgreSQL server; DB tests must not skip}"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p reports
python -m pip check
ruff check app tests ci
ruff format --check app tests ci
PYTHONPYCACHEPREFIX=/tmp/dashboard-syntax python -m compileall -q app tests ci
python -m pytest -q -W error -p no:cacheprovider --junitxml=reports/pytest.xml
python ci/check_results.py reports/pytest.xml
