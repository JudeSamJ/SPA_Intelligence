"""Browser-check launcher: the real app, real OCR (Tesseract behind a stand-in Qwen endpoint), a fake model for extraction only."""
import os, sys
sys.path.insert(0, "/home/user/SPA_Intelligence")
from tests import tesseract_server
srv, base = tesseract_server.start()
for k, v in dict(QWEN_BASE_URL=base, QWEN_API_KEY="k"*20, QWEN_MODEL="qwen-vl-standin", OCR_ENGINE="qwen", OCR_VERIFY="0",
                 SPA_UPLOAD_DIR="/tmp/ocr_ui/up", SPA_CACHE_DIR="/tmp/ocr_ui/cache", SPA_REVIEW_DIR="/tmp/ocr_ui/rev", SPA_ALERTS_PATH="/tmp/ocr_ui/alerts.json",
                 SERVE_FRONTEND="1", SPA_DISABLE_SCHEDULER="1", LLM_PROVIDER="azure_openai", AZURE_OPENAI_DEPLOYMENT="x",
                 AZURE_OPENAI_API_KEY="x", AZURE_OPENAI_ENDPOINT="https://x.invalid/").items():
    os.environ[k] = v
from app.llm import AnthropicAdapter
from tests.fakes import FakeClient, oracle_input
from tests.test_ocr import SAMPLE
import app.extract as ex
ex.get_llm = lambda c=None: AnthropicAdapter(FakeClient(oracle_input(SAMPLE)))
import uvicorn
from backend.api.main import app
uvicorn.run(app, host="127.0.0.1", port=8124, log_level="warning")
