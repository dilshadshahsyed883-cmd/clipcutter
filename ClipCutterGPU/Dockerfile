# syntax=docker/dockerfile:1
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
ARG SOURCE_SHA
LABEL org.opencontainers.image.revision=$SOURCE_SHA
ENV CLIPCUTTER_SOURCE_SHA=$SOURCE_SHA
RUN test -n "$SOURCE_SHA"
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH PORT=8080 CLIPCUTTER_MODEL_DIR=/models \
    CLIPCUTTER_USE_GPU=1 CLIPCUTTER_VIDEO_ENCODER=auto \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates zlib1g libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
WORKDIR /opt/clipcutter
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: -r requirements.txt
COPY worker ./worker
COPY tests ./tests
RUN python -m compileall -q worker && python -c "import av,cv2,numpy,onnxruntime,pydantic; from worker.job import Staged" \
    && groupadd --gid 10001 clipworker && useradd --uid 10001 --gid 10001 --no-create-home clipworker \
    && mkdir /data /models && chown clipworker:clipworker /data
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=3)"
ENTRYPOINT ["python","-m","worker.service"]
