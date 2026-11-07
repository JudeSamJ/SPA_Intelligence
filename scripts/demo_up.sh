#!/usr/bin/env bash
# Demo launcher for Power Automate + Copilot Studio WITHOUT IT help (no Azure hosting, no Entra registrations).
#
#   scripts/demo_up.sh            # builds nothing; needs `npm run build` done once and .env filled
#
# Starts TWO processes that share the same data folder:
#   :8000  your private UI + API, bound to 127.0.0.1, AUTH_MODE=off. Never expose this one.
#   :8001  API only, AUTH_MODE=apikey, bound to 127.0.0.1. THIS is the one you put behind an HTTPS tunnel for Power Platform.
# Then run a tunnel to port 8001 only (see docs/demo-without-it.md). Keys are generated into data/demo_keys.json (gitignored).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
mkdir -p data
if [ ! -f data/demo_keys.json ]; then
  $PY - <<'PYEOF'
import json, secrets, glob, hashlib
from pathlib import Path
sample = next(iter(sorted(glob.glob("samples/sample_a.pdf"))))
cid = hashlib.sha256(Path(sample).read_bytes()).hexdigest()
keys = {"staff": "spa-staff-" + secrets.token_urlsafe(24), "buyer": "spa-buyer-" + secrets.token_urlsafe(24)}
api = {keys["staff"]: {"name": "Demo reviewer", "roles": ["Spa.Reviewer"]},
       keys["buyer"]: {"name": "Demo buyer (sample A)", "roles": ["Spa.Buyer"], "contract": cid}}
Path("data/demo_keys.json").write_text(json.dumps({"keys": keys, "API_KEYS": api, "buyer_contract": "sample_a.pdf"}, indent=2))
print("created data/demo_keys.json")
PYEOF
fi
API_KEYS=$($PY -c "import json;print(json.dumps(json.load(open('data/demo_keys.json'))['API_KEYS']))")
export API_KEYS
trap 'kill 0' EXIT
SERVE_FRONTEND=1 AUTH_MODE=off $PY -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 &
SPA_DISABLE_SCHEDULER=1 SERVE_FRONTEND=0 AUTH_MODE=apikey $PY -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8001 &
echo "UI (private):        http://127.0.0.1:8000"
echo "Connector API:       http://127.0.0.1:8001   (tunnel THIS port; keys in data/demo_keys.json)"
wait
