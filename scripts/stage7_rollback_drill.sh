#!/usr/bin/env bash
set -euo pipefail
GOOD_IMAGE="controlador-trade:stage7-rollback-good"
BAD_IMAGE="controlador-trade:stage7-rollback-bad"
GOOD_CONTAINER="controlador-trade-stage7-good"
BAD_CONTAINER="controlador-trade-stage7-bad"
ARTIFACT_DIR="stage7-rollback-artifact"
mkdir -p "$ARTIFACT_DIR"
cleanup() { docker rm -f "$GOOD_CONTAINER" "$BAD_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker build --tag "$GOOD_IMAGE" .
GOOD_ID="$(docker image inspect "$GOOD_IMAGE" --format '{{.Id}}')"
docker run -d --name "$GOOD_CONTAINER" -p 17860:7860 "$GOOD_IMAGE" >/dev/null
for attempt in {1..30}; do
  if python - <<'PY'
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:17860/api/health", timeout=3) as r:
    p=json.loads(r.read().decode())
    if r.status != 200 or p.get("ok") is not True: raise SystemExit(1)
PY
  then break; fi
  sleep 2
done
python - <<'PY'
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:17860/api/health", timeout=3) as r:
    p=json.loads(r.read().decode())
assert r.status == 200 and p.get("ok") is True
PY
docker rm -f "$GOOD_CONTAINER" >/dev/null

cat > "$ARTIFACT_DIR/Dockerfile.rollback-bad" <<EOF
FROM $GOOD_IMAGE
HEALTHCHECK --interval=2s --timeout=2s --retries=3 CMD ["sh", "-c", "exit 1"]
EOF
docker build --file "$ARTIFACT_DIR/Dockerfile.rollback-bad" --tag "$BAD_IMAGE" .
BAD_ID="$(docker image inspect "$BAD_IMAGE" --format '{{.Id}}')"
docker run -d --name "$BAD_CONTAINER" -p 17860:7860 "$BAD_IMAGE" >/dev/null
sleep 8
BAD_HEALTH="$(docker inspect "$BAD_CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}')"
if [[ "$BAD_HEALTH" != "unhealthy" ]]; then
  echo "candidate release did not enter expected failed health state: $BAD_HEALTH" >&2
  exit 1
fi

docker rm -f "$BAD_CONTAINER" >/dev/null
docker run -d --name "$GOOD_CONTAINER" -p 17860:7860 "$GOOD_IMAGE" >/dev/null
for attempt in {1..30}; do
  if python - <<'PY'
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:17860/api/health", timeout=3) as r:
    p=json.loads(r.read().decode())
    if r.status != 200 or p.get("ok") is not True: raise SystemExit(1)
PY
  then break; fi
  sleep 2
done
python - <<'PY'
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:17860/api/health", timeout=3) as r:
    p=json.loads(r.read().decode())
assert r.status == 200 and p.get("ok") is True
PY

cat > "$ARTIFACT_DIR/rollback-evidence.json" <<EOF
{
  "exercise": "stage7-controlled-container-rollback",
  "scope": "CI-only immutable-container rollback drill; no external production deployment",
  "commit": "${GITHUB_SHA:-unknown}",
  "previous_release_image": "$GOOD_IMAGE",
  "previous_release_image_id": "$GOOD_ID",
  "candidate_release_image": "$BAD_IMAGE",
  "candidate_release_image_id": "$BAD_ID",
  "candidate_failure_state": "$BAD_HEALTH",
  "rollback_result": "HEALTHY",
  "rollback_target": "$GOOD_IMAGE",
  "real_execution": false,
  "external_production_rollback_proven": false
}
EOF
cat "$ARTIFACT_DIR/rollback-evidence.json"
