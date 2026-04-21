"""
core/faiss_indexer.py — FAISS FlatIP index manager with auto-update thread.

Maintains a single flat inner-product index over all images in *image_dir*.
A background daemon thread watches the directory and incrementally indexes
any newly added images without restarting the server.

Usage:
    indexer = FaissIndexer()                          # starts bg thread
    results = indexer.search_similar("query.jpg", top_n=10)
    # → [(image_path, similarity_score), ...]

    progress = indexer.load_progress()
    # → {"processed": int, "total": int, "remaining": int}
"""

import json
import logging
import multiprocessing
import os
import threading
import time

import faiss
import numpy as np

from core.image_processor import ImageProcessor

logger = logging.getLogger(__name__)

# ── Defaults (override via constructor kwargs) ────────────────────────────────
_DEFAULT_IMAGE_DIR = "./static/images"
_DEFAULT_DATA_DIR  = "./data_flat"
_UPDATE_INTERVAL   = 10   # seconds between directory scans
_BATCH_SIZE        = 64   # images per indexing batch
_VECTOR_DIM        = 1024 # beit-large pooler output dimension


class FaissIndexer:
    """Thread-safe FAISS FlatIP index over a directory of images.

    Args:
        image_dir:       Directory that holds the 500×500 source images.
        data_dir:        Directory where index files are persisted to disk.
        update_interval: Seconds between background scans for new images.
        batch_size:      Number of images to accumulate before an index flush.
    """

    def __init__(
        self,
        image_dir: str = _DEFAULT_IMAGE_DIR,
        data_dir: str = _DEFAULT_DATA_DIR,
        update_interval: int = _UPDATE_INTERVAL,
        batch_size: int = _BATCH_SIZE,
    ) -> None:
        self.image_processor   = ImageProcessor()
        self.image_dir         = image_dir
        self.data_dir          = data_dir
        self.update_interval   = update_interval
        self.batch_size        = batch_size

        # File paths for persistence
        self.index_file    = os.path.join(data_dir, "flat_index.bin")
        self.paths_file    = os.path.join(data_dir, "image_paths.npy")
        self.progress_file = os.path.join(data_dir, "indexing_progress.json")

        # Runtime state
        self.index: faiss.Index | None = None
        self.existing_image_paths: list[str] = []   # paths currently in the index
        self.image_paths:          list[str] = []   # all paths discovered on disk

        # Process-safe lock so the bg thread and request threads don't collide
        self.lock = multiprocessing.Lock()
        self._indexing_thread: threading.Thread | None = None

        # ── Startup sequence ──────────────────────────────────────────────────
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(image_dir, exist_ok=True)

        self._load_existing_data()
        self._load_image_paths()
        self._save_progress(len(self.existing_image_paths), len(self.image_paths))
        self._start_indexing_thread()

    # ── Index lifecycle ───────────────────────────────────────────────────────

    def _load_existing_data(self) -> None:
        """Load persisted index + paths from disk, or create a fresh index."""
        try:
            if os.path.exists(self.index_file) and os.path.exists(self.paths_file):
                logger.info("Loading existing FAISS index from %s", self.index_file)
                self.index = faiss.read_index(self.index_file)
                self.existing_image_paths = (
                    np.load(self.paths_file, allow_pickle=True).tolist()
                )
                if faiss.get_num_gpus() > 0:
                    res = faiss.StandardGpuResources()
                    self.index = faiss.index_cpu_to_gpu(res, 0, self.index)
                logger.info("Index loaded: %d vectors", len(self.existing_image_paths))
            else:
                logger.info("No existing index found — creating fresh FlatIP index.")
                self._create_new_index()
        except Exception as exc:
            logger.error("Index load failed: %s — starting fresh.", exc)
            self._create_new_index()

    def _create_new_index(self) -> None:
        """Initialise a new FAISS IndexFlatIP wrapped in IndexIDMap."""
        flat = faiss.IndexFlatIP(_VECTOR_DIM)
        self.index = faiss.IndexIDMap(flat)
        if faiss.get_num_gpus() > 0:
            res = faiss.StandardGpuResources()
            self.index = faiss.index_cpu_to_gpu(res, 0, self.index)
        self.existing_image_paths = []

    def _load_image_paths(self) -> None:
        """Discover all image files inside *image_dir*."""
        if os.path.isdir(self.image_dir):
            self.image_paths = [
                os.path.join(self.image_dir, f)
                for f in os.listdir(self.image_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ]
            logger.info("Discovered %d images in %s", len(self.image_paths), self.image_dir)
        else:
            logger.warning("Image directory not found: %s", self.image_dir)
            self.image_paths = []

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_index(self) -> None:
        """Write the FAISS index and path list to disk."""
        try:
            cpu_index = (
                faiss.index_gpu_to_cpu(self.index)
                if faiss.get_num_gpus() > 0
                else self.index
            )
            faiss.write_index(cpu_index, self.index_file)
            np.save(self.paths_file, self.existing_image_paths)
        except Exception as exc:
            logger.error("Failed to save index: %s", exc)

    def _save_progress(self, processed: int, total: int) -> None:
        """Persist indexing progress as JSON."""
        try:
            with open(self.progress_file, "w") as fh:
                json.dump(
                    {"processed": processed, "total": total, "remaining": total - processed},
                    fh,
                )
        except Exception as exc:
            logger.warning("Could not write progress file: %s", exc)

    def load_progress(self) -> dict:
        """Return current indexing progress.

        Returns:
            dict with keys: processed, total, remaining.
        """
        if os.path.exists(self.progress_file):
            with open(self.progress_file) as fh:
                return json.load(fh)
        return {"processed": 0, "total": 0, "remaining": 0}

    # ── Background indexing thread ─────────────────────────────────────────────

    def _start_indexing_thread(self) -> None:
        """Spawn the background daemon thread (idempotent — will not double-start)."""
        if self._indexing_thread and self._indexing_thread.is_alive():
            return
        self._indexing_thread = threading.Thread(
            target=self._auto_update_loop, daemon=True, name="faiss-indexer"
        )
        self._indexing_thread.start()
        logger.info("Background indexing thread started.")

    def _auto_update_loop(self) -> None:
        """Continuously scan *image_dir* for new images and index them."""
        while True:
            try:
                current = {
                    os.path.join(self.image_dir, f)
                    for f in os.listdir(self.image_dir)
                    if f.lower().endswith((".jpg", ".jpeg", ".png"))
                }
                new_images = [p for p in current if p not in self.existing_image_paths]
                if new_images:
                    logger.info("Found %d new image(s) to index.", len(new_images))
                    self._process_new_images(new_images)
            except Exception as exc:
                logger.error("Auto-update error: %s", exc)
            time.sleep(self.update_interval)

    def _process_new_images(self, new_images: list[str]) -> None:
        """Extract features and add images to the index in batches."""
        total = len(self.image_paths)
        batch_vectors: list[np.ndarray] = []
        batch_paths:   list[str]        = []

        for i, path in enumerate(new_images, start=1):
            features = self.image_processor.extract_features(path)
            if features is not None:
                features /= np.linalg.norm(features)  # L2-normalise → cosine sim
                batch_vectors.append(features)
                batch_paths.append(path)

            # Update progress after every image
            self._save_progress(len(self.existing_image_paths) + len(batch_paths), total)

            # Flush when batch is full or we've reached the last image
            if len(batch_vectors) >= self.batch_size or i == len(new_images):
                self._add_batch(batch_vectors, batch_paths)
                batch_vectors, batch_paths = [], []

    def _add_batch(self, vectors: list[np.ndarray], paths: list[str]) -> None:
        """Append a batch of normalised vectors to the FAISS index (thread-safe)."""
        if not vectors:
            return
        start_id = len(self.existing_image_paths)
        ids = np.arange(start_id, start_id + len(vectors))
        arr = np.array(vectors, dtype="float32")
        with self.lock:
            self.index.add_with_ids(arr, ids)
            self.existing_image_paths.extend(paths)
            self._save_index()

    # ── Public search API ─────────────────────────────────────────────────────

    def search_similar(
        self,
        image_path: str,
        top_n: int = 10,
        similarity_threshold: float = 0.5,
    ) -> list[tuple[str, float]]:
        """Return the *top_n* most similar images to *image_path*.

        Args:
            image_path:           Path to the query image.
            top_n:                Max number of results to return.
            similarity_threshold: Minimum cosine similarity (0–1).

        Returns:
            List of (path, similarity_score) tuples, best match first.
        """
        try:
            query = self.image_processor.extract_features(image_path)
            if query is None:
                return []

            query = (query / np.linalg.norm(query)).astype("float32").reshape(1, -1)

            with self.lock:
                distances, indices = self.index.search(query, top_n)

            results = []
            for idx, dist in zip(indices[0], distances[0]):
                if idx >= 0 and dist >= similarity_threshold:
                    results.append((self.existing_image_paths[int(idx)], float(dist)))
            return results

        except Exception as exc:
            logger.error("Search failed: %s", exc)
            return []

    def restart_indexing(self) -> None:
        """Reset index state and restart the background thread."""
        logger.info("Restarting indexing process.")
        self._load_existing_data()
        self._load_image_paths()
        self._start_indexing_thread()
