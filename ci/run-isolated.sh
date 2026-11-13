#!/usr/bin/env bash
# Only objects created under this invocation's unique owner label are removed.
set -euo pipefail
cd "$(dirname "$0")/.."
run_id="dashboard-ci-$(date +%s)-$$-${RANDOM}"
network="$run_id"
database="$run_id-db"
tests="$run_id-tests"
image="dashboard-ci-tests:$run_id"
runtime_image="dashboard-ci-runtime:$run_id"
mkdir -p reports
cleanup() {
  local status=$?
  trap - EXIT
  docker cp "$tests:/src/reports/." reports/ >/dev/null 2>&1 || true
  for container in "$tests" "$database"; do
    if [ "$(docker inspect -f '{{ index .Config.Labels "dashboard-ci-owner" }}' "$container" 2>/dev/null || true)" = "$run_id" ]; then
      docker rm -fv "$container" >/dev/null || true
    fi
  done
  if [ "$(docker network inspect -f '{{ index .Labels "dashboard-ci-owner" }}' "$network" 2>/dev/null || true)" = "$run_id" ]; then
    docker network rm "$network" >/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT
# Synthetic isolated DB, no host port and no environment credentials.
docker network create --label "dashboard-ci-owner=$run_id" "$network" >/dev/null
docker run -d --name "$database" --label "dashboard-ci-owner=$run_id" --network "$network"   -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=dashboard_test postgres:15 >/dev/null
ready=false
for attempt in $(seq 1 60); do
  if docker exec "$database" pg_isready -U postgres -d dashboard_test >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
[ "$ready" = true ] || { echo 'Owned test PostgreSQL did not start' >&2; exit 1; }
docker build -f ci/test.Dockerfile -t "$image" .
docker run --name "$tests" --label "dashboard-ci-owner=$run_id" --network "$network"   -e "TEST_DATABASE_URL=postgresql://postgres@$database:5432/dashboard_test" "$image"
docker build -f Dockerfile -t "$runtime_image" .
