# Salad startup model provisioning

Existing worker engines require compatible SCRFD det_10g.onnx and ArcFace w600k_r50.onnx. The public InsightFace buffalo_l weights are non-commercial research only, not automatically authorized for commercial workloads. Official terms: https://github.com/deepinsight/insightface/blob/master/README.md and https://github.com/deepinsight/insightface/blob/master/python-package/docs/model_zoo.md. Commercial licensing contact: recognition-oss-pack@insightface.ai. Obtain the applicable rights before supplying weights; no weights bundled or redistributed by this project.

On an authorized machine, compute sha256sum det_10g.onnx w600k_r50.onnx from the trusted original files, record model provenance and license, and place the exact files at a private HTTPS endpoint reachable directly by Salad. Endpoint must return binary files without redirects. Configure Salad secrets:
- CLIPCUTTER_MODEL_LICENSE_CONFIRMED=1 only after actual rights verification
- CLIPCUTTER_DETECTOR_SHA256 and CLIPCUTTER_RECOGNIZER_SHA256: pinned trusted checksums
- CLIPCUTTER_MODEL_BASE_URL: approved HTTPS directory (no credentials/query in URL)
- CLIPCUTTER_MODEL_DOWNLOAD_TOKEN: optional private bearer credential, never commit or expose
- CLIPCUTTER_WORKER_API_TOKEN: separate worker credential

Container UID 10001 owns private /models. Startup verifies any pre-staged files, downloads missing files with size bounds, checks digests before atomic publication, never overwrites an invalid file, then verifies again and performs CUDA inference warmup. Readiness remains false on any error. Model credentials are distinct from worker tokens. No public model URL is hardcoded and no paid Salad instance is started. Private hosting, license authorization, actual trusted hashes and live CUDA acceptance remain pending. Startup download can take longer than existing readiness probe window; use a startup probe or adjusted readiness budget after measuring actual transfer/warmup. Existing image must be replaced with the next verified published candidate for automatic download support.
