# syntax=docker/dockerfile:1
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH PORT=8000 CLIPCUTTER_MODEL_DIR=/models \
    CLIPCUTTER_USE_GPU=1 CLIPCUTTER_VIDEO_ENCODER=auto \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates zlib1g libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
WORKDIR /opt/clipcutter
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY worker ./worker
RUN python -m compileall -q worker && python -c "import av,cv2,numpy,onnxruntime,pydantic; from worker.job import Staged" \
    && groupadd --gid 10001 clipworker && useradd --uid 10001 --gid 10001 --no-create-home clipworker \
    && mkdir /data /models && chown clipworker:clipworker /data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)"
CMD ["python","-m","worker.service"]
