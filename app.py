
import asyncio
import base64
import logging
import os
import re
import sys
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.bg_remover import JewelryBackgroundRemover
from core.faiss_indexer import FaissIndexer
from core.ollama_client import check_ollama_health, get_caption
# Suppress verbose httpx / transformers download logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs("./logs", exist_ok=True)

_log_format = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
_handlers: list[logging.Handler] = [
    logging.StreamHandler(sys.stdout),
    logging.FileHandler("./logs/application.log", mode="a", encoding="utf-8"),
]
logging.basicConfig(level=logging.INFO, format=_log_format, handlers=_handlers)
logger = logging.getLogger("image_search_api")

# ── Configuration ─────────────────────────────────────────────────────────────
UPLOAD_DIR        = "static/upload"
ALLOWED_MIME      = {"image/jpeg", "image/png", "image/jpg"}
ALLOWED_EXT       = {".jpg", ".jpeg", ".png"}
MAX_FILE_BYTES    = 5 * 1024 * 1024   # 5 MB
_SAFE_FILENAME_RE = re.compile(r"[^\w\-.]")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    """Sanitise a filename — strip path separators and dangerous characters."""
    name = os.path.basename(name).strip()                 # strip any path prefix
    name = _SAFE_FILENAME_RE.sub("_", name)               # replace unsafe chars
    return name or "upload"


def _validate_upload(file: UploadFile, data: bytes) -> None:
    """Raise HTTPException if the file fails type or size checks."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Use JPG or PNG.",
        )
    if len(data) > MAX_FILE_BYTES:
        mb = len(data) / 1024 / 1024
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({mb:.1f} MB). Maximum is 5 MB.",
        )


# ── Lifespan — initialise heavy objects once ──────────────────────────────────
faiss_indexer: FaissIndexer | None = None
_bg_remover:   JewelryBackgroundRemover | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global faiss_indexer, _bg_remover
    logger.info("=" * 60)
    logger.info("  Exhibit Group AI Vision Suite  —  starting up")
    logger.info("=" * 60)
    faiss_indexer = FaissIndexer()
    logger.info("FaissIndexer ready ✓")
    _bg_remover = JewelryBackgroundRemover()      # for /api/process (in-memory)
    logger.info("BackgroundRemover ready ✓")
    ollama_up = await check_ollama_health()
    logger.info("Ollama status: %s", '✓ running' if ollama_up else '✗ offline (captions will use fallback)')
    yield
    logger.info("Exhibit Group AI Vision Suite  —  shut down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Exhibit Group AI Vision Suite",
    description=(
        "Image similarity search (FAISS + BEiT) and AI image processing "
        "(Ollama vision caption + rembg background removal)."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve everything under static/ as /static/<path>
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def home():
    """Serve the frontend SPA."""
    return FileResponse("templates/index.html")


@app.get("/api/health", tags=["System"])
async def health():
    """Returns the liveness status of the API and FAISS indexer."""
    loaded = faiss_indexer is not None
    return {
        "status": "ok" if loaded else "degraded",
        "indexer_loaded": loaded,
        "message": "All systems operational" if loaded else "Indexer not yet ready",
    }


@app.get("/api/ollama-health", tags=["System"])
async def ollama_health():
    """Check whether the local Ollama vision model server is reachable."""
    is_up = await check_ollama_health()
    return {
        "status": "online" if is_up else "offline",
        "model":  "moondream",
        "message": "Ollama is running" if is_up else "Ollama not reachable — start with: ollama serve",
    }


@app.get("/progress", tags=["System"])
async def get_progress():
    """Return current FAISS background-indexing progress."""
    return faiss_indexer.load_progress()


@app.post("/restart", tags=["System"])
async def restart_indexing():
    """Trigger a full re-scan and restart of the FAISS indexing thread."""
    faiss_indexer.restart_indexing()
    return {"message": "Indexing process restarted."}


@app.post("/search", tags=["Search"])
async def search(
    query_image: UploadFile = File(..., description="Query image (JPG/PNG, max 5 MB)"),
    top_n: int = Form(default=10, ge=1, le=50, description="Number of results to return"),
):
    """
    Similarity search: upload a query image, get back the *top_n* most
    visually similar images as base64-encoded JSON.

    Response shape:
        { "results": [ { "image": "<base64>", "similarity": 0.95, "name": "file.jpg" }, … ] }
    """
    # ── 1. Read & validate ────────────────────────────────────────────────────
    image_bytes = await query_image.read()
    _validate_upload(query_image, image_bytes)

    # ── 2. Persist query image to disk ────────────────────────────────────────
    safe_name  = _safe_filename(query_image.filename or "query.jpg")
    query_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(query_path, "wb") as fh:
        fh.write(image_bytes)

    # ── 3. Run FAISS search ───────────────────────────────────────────────────
    try:
        results = faiss_indexer.search_similar(query_path, top_n=top_n)
    except Exception as exc:
        logger.error("Search failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail="Search processing failed.")

    # ── 4. Build response payload ─────────────────────────────────────────────
    query_b64 = base64.b64encode(image_bytes).decode()
    payload: list[dict] = []

    for img_path, similarity in results:
        try:
            with open(img_path, "rb") as fh:
                payload.append({
                    "image":      base64.b64encode(fh.read()).decode(),
                    "similarity": round(float(similarity), 4),
                    "name":       os.path.basename(img_path),
                })
        except OSError as exc:
            logger.warning("Could not read result image %s: %s", img_path, exc)

    # Prepend the query image itself as the first (exact-match) result
    if payload and payload[0]["similarity"] < 1.0:
        if len(payload) >= top_n:
            payload.pop()
        payload.insert(0, {"image": query_b64, "similarity": 1.0, "name": safe_name})

    logger.info("Search complete: %d result(s) returned.", len(payload))
    return {"results": payload}


@app.post("/api/process", tags=["Image Processing"])
async def process_image(
    file: UploadFile = File(..., description="Image to describe and remove background from"),
):
    """
    AI Image Processing pipeline (runs in parallel):
    1. **Ollama moondream** — generate a one-sentence image description
    2. **rembg** — remove the image background, return PNG

    Response:
        { "description": "...", "image": "<base64-PNG>", "ollama_available": true }
    """
    image_bytes = await file.read()
    _validate_upload(file, image_bytes)

    loop = asyncio.get_event_loop()

    # Run caption (async) + bg removal (CPU-bound → thread) in parallel
    caption_task = get_caption(image_bytes)
    bg_task      = loop.run_in_executor(None, _bg_remover.remove_bg_from_bytes, image_bytes)

    try:
        description, bg_bytes = await asyncio.gather(caption_task, bg_task)
    except Exception as exc:
        logger.error("Processing pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")

    result_b64 = base64.b64encode(bg_bytes).decode() if bg_bytes else None

    ollama_ok = not description.startswith("Vision model unavailable")
    logger.info("Image processing complete — ollama=%s, bg_removed=%s", ollama_ok, result_b64 is not None)

    return {
        "description":      description,
        "image":            result_b64,
        "ollama_available": ollama_ok,
    }


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(413)
async def too_large(_: Request, exc: Exception):
    return JSONResponse(
        status_code=413,
        content={"error": "File too large", "detail": getattr(exc, "detail", str(exc))},
    )


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── Dev entry-point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
