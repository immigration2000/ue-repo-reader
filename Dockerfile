# ue-repo-reader MCP server — deploy anywhere that runs a container with a public HTTPS URL
# (Hugging Face Spaces, Render, Railway, Fly.io, Google Cloud Run, your own server…).
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git git-lfs ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && git lfs install --system

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY scripts ./scripts
COPY server ./server

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=7860 \
    UE_READER_DATA=/data \
    UE_READER_WORKERS=2 \
    UE_REPO_READER_CACHE=/opt/ue-reader-cache

# Fetch the pinned .uasset parser at build time so the first analysis starts immediately.
RUN python -c "import sys; sys.path.insert(0, 'scripts'); import bp_reader; bp_reader.ensure_uasset_read()" \
 && useradd -m -u 1000 app \
 && mkdir -p /data \
 && chown -R app /data /opt/ue-reader-cache

USER app
EXPOSE 7860
CMD ["python", "server/server.py"]
