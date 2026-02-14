from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

app = FastAPI()

# IMPORTANT:
# Keep web files at the REPO ROOT (same folder as main.py).
# This avoids the Render error: "Directory '/code/static' does not exist".

# Serve assets (logos, images)
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/")
def home():
    return FileResponse(str(BASE_DIR / "index.html"))


@app.get("/budgets_2025.json")
def budgets_2025():
    return FileResponse(str(BASE_DIR / "budgets_2025.json"), media_type="application/json")


@app.get("/health")
def health():
    return {"ok": True}
