# ── Base image ────────────────────────────────────────────────────────────────
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

WORKDIR /app

# System deps (OpenCV & Pillow)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure runtime directories exist
RUN mkdir -p /app/logs /app/static/upload /app/static/images /app/data_flat

EXPOSE 5000

# Run using the root-level app.py with Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
