# Hugging Face Space (SDK: Docker) for the ue-repo-reader MCP server.
# Upload this file and README.md to a new Docker Space. It pulls the latest code from GitHub at build time;
# use "Factory rebuild" in the Space settings to update.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git git-lfs ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && git lfs install --system

ARG REPO=https://github.com/immigration2000/ue-repo-reader
ARG REF=main
RUN git clone --depth 1 --branch "$REF" "$REPO" /app
WORKDIR /app
RUN pip install --no-cache-dir -r server/requirements.txt

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=7860 \
    UE_READER_DATA=/data \
    UE_READER_WORKERS=2 \
    UE_REPO_READER_CACHE=/opt/ue-reader-cache

RUN python -c "import sys; sys.path.insert(0, 'scripts'); import bp_reader; bp_reader.ensure_uasset_read()" \
 && useradd -m -u 1000 app \
 && mkdir -p /data \
 && chown -R app /data /opt/ue-reader-cache

USER app
EXPOSE 7860
CMD ["python", "server/server.py"]
