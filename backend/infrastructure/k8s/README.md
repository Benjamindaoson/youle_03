# K8s manifests(Sprint 6 填充)

V1 prod 部署见 `docs/ARCHITECTURE.md §8.2`,资源约 30 vCPU / 80 GB / 4 GPU 节点。

待补:
- backend Deployment + Service + HPA
- agents × 4 Deployment(text / document / image / av;av 需 GPU)
- mcp_servers × 7 Deployment(image-tools / video-tools 需 GPU)
- celery-worker-video Deployment(GPU)
- litellm-proxy Deployment + ConfigMap(L1 / L2)
- frontend(SSR)Deployment
- qdrant StatefulSet
- bge-m3-service Deployment(GPU)
- Sealed Secrets(JWT / API keys / DB / OSS)
- Nginx Ingress
- ArgoCD Application 定义
