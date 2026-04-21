"""
core/bg_remover.py — Jewelry background removal utility.

Uses the `rembg` library with the isnet-general-use model.
Applies contrast + sharpness enhancement before removal so that
jewelry detail is preserved against complex backgrounds.

Usage:
    remover = JewelryBackgroundRemover()
    success = remover.remove_background("path/to/image.jpg")
    # Output saved to static/preprocessed/<name>.png
"""

import os
import logging
from PIL import Image, ImageEnhance
from rembg import new_session, remove

logger = logging.getLogger(__name__)


class JewelryBackgroundRemover:
    """Remove backgrounds from jewelry images and cache the result as PNG.

    Args:
        model_name: rembg session model name (default: isnet-general-use).
        output_dir: Directory where processed PNGs are written.
    """

    def __init__(
        self,
        model_name: str = "isnet-general-use",
        output_dir: str = "static/preprocessed",
    ) -> None:
        self.session = new_session(model_name)
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Preprocessing helpers ─────────────────────────────────────────────────

    @staticmethod
    def _add_contrast_bg(image: Image.Image, bg_color: tuple = (240, 240, 240)) -> Image.Image:
        """Composite the image onto a neutral grey background (RGBA → RGB helper)."""
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        bg = Image.new("RGBA", image.size, bg_color + (255,))
        bg.paste(image, mask=image.getchannel("A"))
        return bg

    @staticmethod
    def _preprocess(image: Image.Image) -> Image.Image:
        """Apply contrast + sharpness boost before BG removal."""
        if image.mode != "RGB":
            image = image.convert("RGB")
        image = JewelryBackgroundRemover._add_contrast_bg(image)
        image = ImageEnhance.Contrast(image).enhance(1.3)
        image = ImageEnhance.Sharpness(image).enhance(1.2)
        return image

    # ── Public API ────────────────────────────────────────────────────────────

    def remove_bg_from_bytes(self, image_bytes: bytes) -> bytes | None:
        """Remove background from raw image bytes and return PNG bytes.

        No disk I/O — used by the ``/api/process`` API route.

        Args:
            image_bytes: Raw bytes of the source image.

        Returns:
            PNG bytes with transparent/white background, or None on error.
        """
        import io as _io
        try:
            image = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
            image = self._preprocess(image)
            result = remove(image, session=self.session)
            buf = _io.BytesIO()
            result.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            logger.error("In-memory BG removal failed: %s", exc)
            return None

    def remove_background(self, image_path: str) -> bool:
        """Remove background from *image_path* and write PNG to *output_dir*.

        Args:
            image_path: Absolute or relative path to the source image.

        Returns:
            True on success, False on any error.
        """
        try:
            image = Image.open(image_path).convert("RGB")
            image = self._preprocess(image)
            result = remove(image, session=self.session)

            # Flatten transparency to RGB for downstream BEiT processing
            if result.mode == "RGBA":
                result = result.convert("RGB")

            base = os.path.splitext(os.path.basename(image_path))[0]
            out_path = os.path.join(self.output_dir, f"{base}.png")
            result.save(out_path, format="PNG", quality=95)
            logger.debug("BG removed: %s → %s", image_path, out_path)
            return True

        except Exception as exc:
            logger.error("BG removal failed for %s: %s", image_path, exc)
            return False
