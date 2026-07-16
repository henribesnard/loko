# ---- Stage 1: Build frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /app/desktop
COPY desktop/package.json desktop/package-lock.json ./
RUN npm ci
COPY desktop/ ./
RUN npm run build

# ---- Stage 2: Download base model (A2) ----
FROM python:3.12-slim AS model-download
RUN pip install --no-cache-dir huggingface_hub
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', \
                  local_dir='/models/base/minilm', \
                  ignore_patterns=['onnx/*', 'openvino/*', 'tf_model*', 'pytorch_model*', \
                                   'rust_model*', 'flax_model*', '.cache/*', '.gitattributes'])"

# ---- Stage 3: Python backend ----
FROM python:3.12-slim
WORKDIR /app

# System deps for ML (scipy, sklearn used by setfit/sentence-transformers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch first (avoids pulling CUDA wheels — A1)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install Python dependencies (server + ML) with constraints (A1)
# Two-step: deps first (cached layer), then package install with source
COPY pyproject.toml constraints-ml.txt ./
RUN mkdir -p loko && touch loko/__init__.py && \
    pip install --no-cache-dir -c constraints-ml.txt ".[server,ml]" && \
    rm -rf loko/

# Remove build-essential (only needed for compiling C extensions above)
RUN apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy backend source and install package (no-deps, source only)
COPY loko/ ./loko/
RUN pip install --no-cache-dir --no-deps .

# A2: copy pre-downloaded base model to fixed local path
COPY --from=model-download /models/base/minilm /app/models/base/minilm

# Copy widget
COPY widget/ ./widget/

# Copy built frontend
COPY --from=frontend-build /app/desktop/dist ./desktop/dist

# REMOVED: eval/ datasets (client-specific, purged)
# Generic evaluation tools remain in loko/eval/ (copied with loko/ below)
COPY tools/ ./tools/

# Create non-root user for security
RUN groupadd --gid 1000 loko && \
    useradd --uid 1000 --gid loko --create-home loko && \
    mkdir -p /home/loko/.loko && chown -R loko:loko /home/loko/.loko

# Data volume for bot configs & sessions
VOLUME /home/loko/.loko

# Environment variables (A2, A6)
# Required:
#   LOKO_ADMIN_TOKEN — admin API authentication token
# ML / Offline:
#   LOKO_ML=on — enable ML features (default: on; off → /train returns 503)
#   LOKO_BASE_MODEL_PATH — local path for base sentence-transformer model
#   HF_HUB_OFFLINE=1 — block all Hugging Face hub network access
#   TRANSFORMERS_OFFLINE=1 — block transformers library network access
# Server:
#   LOKO_MODE=server — enables server mode (requires LOKO_ADMIN_TOKEN)
#   LOKO_CORS_ORIGINS — comma-separated list of allowed CORS origins
#   LOKO_SESSION_RETENTION_DAYS=30 — session data retention (RGPD)
#   LOKO_DATA_DIR — custom data directory (default: ~/.loko)
#   LOKO_ESCALATION_PROVIDER — set to "mock" to allow MockEscalationProvider

ENV LOKO_MODE=server
ENV LOKO_ML=on
ENV LOKO_BASE_MODEL_PATH=/app/models/base/minilm
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HOME=/app/.hf_cache

EXPOSE 8000

USER loko

CMD ["uvicorn", "loko.main:app", "--host", "0.0.0.0", "--port", "8000"]
