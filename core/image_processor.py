"""
core/image_processor.py — BEiT-based image feature extractor.

Loads microsoft/beit-large-patch16-224 once at class construction time.
For each image it:
  1. Calls JewelryBackgroundRemover to strip the background (cached PNG).
  2. Feeds the cleaned image through BEiT and returns the [CLS] pooler output
     as a 1-D float32 numpy array (1024-d for beit-large).

Usage:
    processor = ImageProcessor()
    vector = processor.extract_features("path/to/image.jpg")  # np.ndarray | None
"""

import os
import logging
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError
import torch
from transformers import BeitImageProcessor, BeitModel

from core.bg_remover import JewelryBackgroundRemover

logger = logging.getLogger(__name__)

_MODEL_NAME = "microsoft/beit-large-patch16-224"
_PREPROCESSED_DIR = "static/preprocessed"


class ImageProcessor:
    """Extract BEiT feature vectors from jewelry images.

    The model is loaded once during ``__init__``; the instance is then
    safe to reuse across many calls.
    """

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        try:
            self.feature_extractor = BeitImageProcessor.from_pretrained(model_name)
            self.model = BeitModel.from_pretrained(model_name)
            self.model.eval()
            self.bg_remover = JewelryBackgroundRemover(output_dir=_PREPROCESSED_DIR)
            logger.info("ImageProcessor ready (model: %s)", model_name)
        except Exception as exc:
            logger.error("Failed to load BEiT model: %s", exc)
            raise

    def extract_features(self, img_path: str) -> np.ndarray | None:
        """Return the BEiT pooler-output vector for *img_path*, or None on failure.

        Args:
            img_path: Path to the source image (JPEG / PNG).

        Returns:
            1-D float32 numpy array, or None if processing fails.
        """
        try:
            # ── 1. Derive the pre-processed (BG-removed) path ────────────────
            base = os.path.splitext(os.path.basename(img_path))[0]
            preprocessed_path = os.path.join(_PREPROCESSED_DIR, f"{base}.png")

            # ── 2. Run BG removal if not already cached ───────────────────────
            if not os.path.exists(preprocessed_path):
                self.bg_remover.remove_background(img_path)

            if not os.path.exists(preprocessed_path):
                logger.warning("Pre-processed image missing, using original: %s", img_path)
                preprocessed_path = img_path

            # ── 3. Load image + run BEiT inference ────────────────────────────
            image = Image.open(preprocessed_path)
            inputs = self.feature_extractor(images=image, return_tensors="pt")

            with torch.no_grad():
                outputs = self.model(**inputs)

            features: np.ndarray = outputs.pooler_output.cpu().numpy().flatten()
            logger.debug("Features extracted: %s", img_path)
            return features

        except (UnidentifiedImageError, OSError, ValueError) as exc:
            logger.warning("Skipping %s: %s", img_path, exc)
            return None
