"""Modal deployment wrapper for the CompAud (PS3) FastAPI backend.

First time (under your own Modal account):

    pip install modal && modal setup          # authenticate

Run locally (hot-reload, ephemeral URL):

    cd backend && modal serve modal_app.py

Deploy (persistent URL):

    cd backend && modal deploy modal_app.py

Env / secrets:

    Runtime config (OPENAI_*, optional NEO4J_*, FRONTEND_ORIGIN, etc.) is pulled
    from a Modal Secret built from the repo `.env` at deploy time via
    `Secret.from_dotenv`. PHOENIX_* is forced off in the container (no local
    collector). Set FRONTEND_ORIGIN in `.env` to your deployed Vercel URL so CORS
    allows it. The embedding model is baked into the image at build time.
"""

from __future__ import annotations

from pathlib import Path

import modal

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

CONTAINER_REPO = "/root/repo"
CONTAINER_BACKEND = f"{CONTAINER_REPO}/backend"

def _cache_embedding_model() -> None:
    """Bake the embedding model into the image at build time so cold containers
    never download it from HuggingFace on the first request."""
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("BAAI/bge-small-en-v1.5")


image = (
    modal.Image.debian_slim(python_version="3.12")
    # CPU-only torch first so sentence-transformers doesn't pull the large CUDA
    # wheel. If the build ever fails resolving torch, remove this line and let
    # sentence-transformers install its default torch.
    .pip_install("torch>=2.2", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install(
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "pydantic-settings>=2.7.0",
        "python-multipart>=0.0.20",
        "langgraph>=0.2.0",
        "neo4j>=5.28.0",
        "openai>=1.50.0",
        "opentelemetry-api>=1.42.0",
        "opentelemetry-sdk>=1.42.0",
        "opentelemetry-exporter-otlp>=1.42.0",
        "arize-phoenix-otel>=0.16.0",
        # PS3 pipeline deps
        "sentence-transformers>=3.0",
        "reportlab>=4",
        "pandas>=2.2",
        "scikit-learn>=1.5",
        "numpy>=1.26",
    )
    .run_function(_cache_embedding_model)
    .env({"PYTHONPATH": CONTAINER_BACKEND})
    .workdir(CONTAINER_BACKEND)
    # Local files are added last (Modal requires local mounts after build steps).
    .add_local_dir(str(BACKEND_DIR / "app"), f"{CONTAINER_BACKEND}/app")
    .add_local_dir(str(PROJECT_ROOT / "docs"), f"{CONTAINER_REPO}/docs")
    # PS3 data + collector inputs (resolve under REPO_ROOT=/root/repo at runtime).
    .add_local_dir(
        str(PROJECT_ROOT / "Problem_03_Compliance_Evidence" / "sample_data"),
        f"{CONTAINER_REPO}/Problem_03_Compliance_Evidence/sample_data",
    )
    .add_local_dir(str(BACKEND_DIR / "sample_inputs"), f"{CONTAINER_BACKEND}/sample_inputs")
)

app = modal.App("compaud-ps3-backend", image=image)

runtime_secret = modal.Secret.from_dotenv(path=PROJECT_ROOT)


@app.function(
    secrets=[runtime_secret],
    timeout=600,
    min_containers=0,
    max_containers=5,
    cpu=2.0,
    memory=4096,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def fastapi_app():
    import os

    os.environ["PHOENIX_ENABLED"] = "false"
    # LLM narratives on by default for the hosted demo; set "false" for faster/cheaper runs.
    os.environ.setdefault("PS3_LLM_NARRATIVES", "true")
    # Allowed browser origins: your deployed frontend + local dev. Set FRONTEND_ORIGIN
    # in .env (flows in via Secret.from_dotenv) to your Vercel URL once deployed.
    _frontend = os.environ.get("FRONTEND_ORIGIN", "").strip()
    os.environ["CORS_ORIGINS"] = ",".join(
        origin for origin in [_frontend, "http://localhost:3000"] if origin
    )

    from app.main import app as fastapi

    return fastapi
