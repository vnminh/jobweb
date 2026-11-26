# JobWeb API + JobUNICORN recommender (CPU). Build context: repository root.
FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    JOBUNICORN_REPO=/app/jobunicorn \
    JOBWEB_CACHE=/app/cache \
    PYTHONPATH=/app/jobunicorn/src

# 1) Python dependencies (CPU-only torch)
COPY docker/requirements-backend.txt /tmp/req.txt
RUN pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r /tmp/req.txt

# 2) text encoder used for jobs/users created on the web (baked in, no download at runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# 3) processed CareerBuilder data the recommender reads (~2.1 GB, see docker/data_files.txt) + encoder cache
COPY docker/assets/data /app/jobunicorn/data
COPY docker/assets/cache /app/cache

# 4) code and trained checkpoints
COPY jobunicorn /app/jobunicorn
COPY backend /app/backend

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["python", "-W", "ignore", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
