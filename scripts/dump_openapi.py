"""Write the FastAPI OpenAPI schema to a file (used by `npm run gen:api` in frontend/)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.api.main import app  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
out.write_text(json.dumps(app.openapi(), indent=2))
print(f"wrote {out} ({len(app.openapi()['paths'])} paths)")
