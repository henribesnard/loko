# ---- Stage 1: Build frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/desktop
COPY desktop/package.json desktop/package-lock.json ./
RUN npm ci
COPY desktop/ ./
RUN npm run build

# ---- Stage 2: Python backend (A1a — single image with CPU-only torch) ----
FROM python:3.12-slim
WORKDIR /app

# System deps for ML (scipy, sklearn used by setfit/sentence-transformers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch first (avoids pulling CUDA wheels)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install Python dependencies (server + ML)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[server,ml]"

# Pre-download the base model into HF_HOME (A1 — no HF dependency at runtime)
ENV HF_HOME=/app/.hf_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')" \
    || echo "Warning: model pre-download failed, will download at first training"

# Copy backend source
COPY loko/ ./loko/

# Copy widget
COPY widget/ ./widget/

# Copy built frontend
COPY --from=frontend-build /app/desktop/dist ./desktop/dist

# Data volume for bot configs & sessions
VOLUME /root/.loko

# Environment variables documented for production
# Required:
#   LOKO_ADMIN_TOKEN — admin API authentication token
# Optional:
#   RAGKIT_MODE=server — enables server mode (requires LOKO_ADMIN_TOKEN)
#   RAGKIT_CORS_ORIGINS — comma-separated list of allowed CORS origins
#   LOKO_SESSION_RETENTION_DAYS=30 — session data retention (RGPD)
#   LOKO_DATA_DIR — custom data directory (default: ~/.loko)
#   LOKO_ML=on — enable ML features (default: on)

ENV RAGKIT_MODE=server

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "loko.main:app", "--host", "0.0.0.0", "--port", "8000"]
