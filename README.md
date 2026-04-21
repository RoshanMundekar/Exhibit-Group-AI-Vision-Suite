# Exhibit Group — AI Vision Suite

<div align="center">
  <img src="static/uilogo/logo-light.png" alt="Exhibit Group Logo" height="60" />
  <br/><br/>
  <strong>Production-grade AI Vision platform built with FastAPI</strong>
  <br/>
  Image Similarity Search · AI Image Captioning · Background Removal
  <br/><br/>

  ![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
  ![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)
  ![FAISS](https://img.shields.io/badge/FAISS-CPU%2FGPU-4B8BBE?style=flat)
  ![BEiT](https://img.shields.io/badge/BEiT-Large--1024d-7B2FBE?style=flat)
  ![rembg](https://img.shields.io/badge/rembg-isnet--general--use-10B981?style=flat)
  ![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat&logo=docker&logoColor=white)
</div>

---

---

## Demo Video
Watch here:https://drive.google.com/file/d/16vuE3EBVLdSJSdzdKWFOQZj0ls1AsBQv/view?usp=sharing

---

## 📋 Table of Contents

- [Features](#-features)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Quick Start — Local (No Docker)](#-quick-start--local-no-docker)
- [Run with Docker](#-run-with-docker)
- [Run with Docker Compose](#-run-with-docker-compose-recommended)
- [API Reference](#-api-reference)
- [Architecture](#-architecture)
- [Configuration](#-configuration)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Features

| Feature | Endpoint | Description |
|---------|----------|-------------|
| 🔍 **Image Similarity Search** | `POST /search` | Upload a query image → find the most visually similar images using **FAISS + BEiT** |
| 🤖 **AI Image Processing** | `POST /api/process` | Describe an image with **Ollama moondream** + remove its background with **rembg** — in parallel |
| 📊 **Index Progress** | `GET /progress` | Live FAISS indexing progress (auto-updated every 10 s) |
| 🔄 **Restart Indexing** | `POST /restart` | Force a full re-scan of the image directory |
| ❤️ **Health Check** | `GET /api/health` | API + FAISS indexer liveness |
| 🧠 **Ollama Status** | `GET /api/ollama-health` | Check if Ollama vision model is reachable |
| 📄 **Swagger UI** | `GET /docs` | Interactive API documentation |

---

## 🗂️ Project Structure

```
Exhibit_Group/
│
├── app.py                      ← FastAPI application — all routes & lifespan
│
├── core/                       ← Internal ML & utility package
│   ├── __init__.py
│   ├── bg_remover.py           ← JewelryBackgroundRemover (rembg + PIL enhancing)
│   ├── image_processor.py      ← BEiT feature extractor (uses bg_remover)
│   ├── faiss_indexer.py        ← FAISS FlatIP index — search, auto-index thread
│   └── ollama_client.py        ← Async Ollama vision API client (httpx)
│
├── templates/
│   └── index.html              ← Responsive SPA (Tailwind CSS, sidebar, dark mode)
│
├── static/
│   ├── uilogo/
│   │   └── logo-light.png      ← Exhibit Group brand logo
│   ├── images/                 ← ⬅ PUT YOUR SOURCE IMAGES HERE
│   ├── upload/                 ← Temporary query image storage (auto-created)
│   └── preprocessed/           ← BG-removed PNG cache (auto-created)
│
├── data_flat/                  ← FAISS index files (auto-created at runtime)
│   ├── flat_index.bin
│   ├── image_paths.npy
│   └── indexing_progress.json
│
├── logs/
│   └── application.log
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env                        ← Environment variables (never commit)
├── .env.example                ← Template — commit this instead
└── .gitignore
```

---

## ✅ Prerequisites

### Required
| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://python.org) |
| pip | latest | bundled with Python |

### Optional (for AI captioning feature)
| Tool | Purpose | Install |
|------|---------|---------|
| [Ollama](https://ollama.ai) | Run moondream vision model locally | [ollama.ai](https://ollama.ai) |
| Docker + Docker Compose | Containerised deployment | [docker.com](https://docker.com) |
| NVIDIA GPU + Container Toolkit | GPU acceleration | [NVIDIA docs](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit) |

> **Note:** Ollama is **optional**. If it is not running, the Image Processing feature still works — background removal succeeds and the description gracefully returns `"Vision model unavailable"`.

---

## 🚀 Quick Start — Local (No Docker)

### Step 1 — Clone the repo

```bash
git clone <repo-url>
cd Exhibit_Group
```

### Step 2 — Create a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

> **GPU users:** swap `faiss-cpu` → `faiss-gpu` and `onnxruntime` → `onnxruntime-gpu` in `requirements.txt` before installing.

### Step 4 — Add your images

Copy your source images (JPG / PNG) into the `static/images/` folder:

```bash
# Windows
copy "C:\path\to\your\images\*.jpg" static\images\

# macOS / Linux
cp /path/to/your/images/*.jpg static/images/
```

The background indexing thread will pick them up automatically.

### Step 5 — (Optional) Start Ollama for AI captions

```bash
# Install moondream model (first time only — ~1.7 GB)
ollama pull moondream

# Start Ollama server
ollama serve
```

### Step 6 — Start the server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### Step 7 — Open in browser

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | ✨ Main dashboard UI |
| `http://localhost:8000/docs` | 📄 Swagger interactive API |
| `http://localhost:8000/redoc` | 📘 ReDoc API reference |

---

## 🐳 Run with Docker

### Build the image

```bash
docker build -t exhibit-group-vision .
```

### Run (CPU mode)

```bash
docker run -d \
  --name exhibit_vision \
  -p 8000:5000 \
  -v $(pwd)/static/images:/app/static/images \
  -v $(pwd)/data_flat:/app/data_flat \
  -v $(pwd)/logs:/app/logs \
  exhibit-group-vision
```

> **Windows PowerShell:**
> ```powershell
> docker run -d `
>   --name exhibit_vision `
>   -p 8000:5000 `
>   -v ${PWD}/static/images:/app/static/images `
>   -v ${PWD}/data_flat:/app/data_flat `
>   -v ${PWD}/logs:/app/logs `
>   exhibit-group-vision
> ```

### Run (GPU mode)

```bash
docker run -d \
  --name exhibit_vision \
  --gpus all \
  -p 8000:5000 \
  -v $(pwd)/static/images:/app/static/images \
  -v $(pwd)/data_flat:/app/data_flat \
  -v $(pwd)/logs:/app/logs \
  exhibit-group-vision
```

---

## 🐙 Run with Docker Compose (Recommended)

### CPU-only mode

```bash
docker compose up --build
```

### With GPU support

```bash
docker compose --profile gpu up --build
```

### With Ollama vision model

```bash
docker compose --profile ollama up --build
```

### Full stack (GPU + Ollama)

```bash
docker compose --profile gpu --profile ollama up --build
```

### Access the app

```
http://localhost:8000
```

### Stop

```bash
docker compose down
```

### Stop and remove volumes (full reset)

```bash
docker compose down -v
```

---

## 🌐 API Reference

### `GET /api/health`
Returns API + FAISS indexer status.

```bash
curl http://localhost:8000/api/health
```
```json
{ "status": "ok", "indexer_loaded": true, "message": "All systems operational" }
```

---

### `GET /api/ollama-health`
Checks if Ollama vision model is reachable.

```bash
curl http://localhost:8000/api/ollama-health
```
```json
{ "status": "online", "model": "moondream", "message": "Ollama is running" }
```

---

### `POST /search`
Find the most visually similar images to a query image.

**Form fields:**

| Field | Type | Required | Default | Limit |
|-------|------|----------|---------|-------|
| `query_image` | file | ✅ | — | JPG/PNG, max 5 MB |
| `top_n` | integer | ❌ | `10` | 1–50 |

```bash
curl -X POST http://localhost:8000/search \
  -F "query_image=@ring.jpg" \
  -F "top_n=6"
```

**Response:**
```json
{
  "results": [
    { "name": "ring.jpg",         "similarity": 1.0,    "image": "<base64>" },
    { "name": "similar_ring.jpg", "similarity": 0.9312, "image": "<base64>" }
  ]
}
```

> The query image is always prepended as the first result with `similarity: 1.0`.

---

### `POST /api/process`
Run the full AI pipeline: **Ollama caption** + **background removal** (in parallel).

| Field | Type | Required | Limit |
|-------|------|----------|-------|
| `file` | file | ✅ | JPG/PNG, max 5 MB |

```bash
curl -X POST http://localhost:8000/api/process \
  -F "file=@product.jpg"
```

**Response:**
```json
{
  "description":      "A gold diamond ring with an oval cut stone on a white surface.",
  "image":            "<base64-PNG>",
  "ollama_available": true
}
```

---

### `GET /progress`
Live FAISS indexing progress.

```bash
curl http://localhost:8000/progress
```
```json
{ "processed": 342, "total": 500, "remaining": 158 }
```

---

### `POST /restart`
Trigger a full re-scan of `static/images/` and restart the indexing thread.

```bash
curl -X POST http://localhost:8000/restart
```
```json
{ "message": "Indexing process restarted." }
```

---

## ⚙️ Architecture

```
Browser / API Client
        │
        ▼
   app.py  (FastAPI — async)
        │
        ├── POST /search
        │     ├── Validate file (ext + size)
        │     ├── Save to static/upload/
        │     ├── FaissIndexer.search_similar()
        │     │     └── ImageProcessor.extract_features()
        │     │           ├── JewelryBackgroundRemover  →  static/preprocessed/<name>.png
        │     │           └── BeitModel forward pass   →  1024-d float32 vector
        │     └── FAISS IndexFlatIP.search()  (cosine sim via L2 normalisation)
        │
        ├── POST /api/process        (asyncio.gather → parallel execution)
        │     ├── get_caption()      →  Ollama moondream over HTTP (httpx)
        │     └── remove_bg_from_bytes()  →  rembg in-memory PNG
        │
        └── Background Thread  (FaissIndexer._auto_update_loop)
              └── Polls static/images/ every 10 s → indexes new files
```

**Design decisions:**
- Singleton `FaissIndexer` + `JewelryBackgroundRemover` — loaded **once** at startup via FastAPI `lifespan`
- `multiprocessing.Lock` guards all FAISS `add_with_ids()` + disk writes (thread-safe)
- BG-removal cache at `static/preprocessed/` — redundant re-runs are skipped
- L2-normalised vectors → inner-product ≡ cosine similarity
- Ollama is **optional** — graceful fallback string if offline

---

## 🔧 Configuration

| Variable | File | Default | Description |
|----------|------|---------|-------------|
| `image_dir` | `core/faiss_indexer.py` | `./static/images` | Source image directory |
| `data_dir` | `core/faiss_indexer.py` | `./data_flat` | FAISS index storage |
| `update_interval` | `core/faiss_indexer.py` | `10` (sec) | BG scan interval |
| `OLLAMA_BASE_URL` | `core/ollama_client.py` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `core/ollama_client.py` | `moondream` | Vision model name |
| `MAX_FILE_BYTES` | `app.py` | `5 MB` | Upload size limit |
| Port | `docker-compose.yml` | `8000` (host) | Mapped from 5000 (container) |

---

## 🛠️ Troubleshooting

### Model takes long to download on first start
The BEiT model (`~1.3 GB`) and rembg model (`~170 MB`) are downloaded from HuggingFace on first run.
This is one-time only; subsequent starts use the local cache.

```bash
# Pre-warm the cache manually (optional)
python -c "from core.image_processor import ImageProcessor; ImageProcessor()"
```

### Ollama not available
```bash
# Check Ollama is installed and running
ollama serve
ollama pull moondream   # if model not yet downloaded

# Verify
curl http://localhost:11434/api/tags
```

### No similar images returned
- Ensure source images are in `static/images/`
- Check indexing progress at `GET /progress`
- Wait for the background thread to finish (watch `logs/application.log`)

### Docker GPU not detected
```bash
# Verify NVIDIA toolkit
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### Permission errors on Linux/macOS
```bash
chmod -R 755 static/ data_flat/ logs/
```

---

## 📄 License

MIT — © 2026 Exhibit Group
