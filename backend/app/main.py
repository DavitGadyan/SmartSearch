import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1 import acp
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis
from app.services.acp_service import AcpError
from app.services.runtime import runtime

configure_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting %s v%s (env=%s)", settings.app_name, __version__, settings.env)
    await runtime.load()
    yield
    await close_redis()
    log.info("shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Commerce Intelligence Engine: hybrid search, learning-to-rank, personalization, "
        "recommendations, behavioral event tracking and an A/B experimentation engine."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)


STATIC_CACHE = "public, max-age=86400, stale-while-revalidate=604800"


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", STATIC_CACHE)
    elif request.url.path not in ("/health", "/"):
        log.info("%s %s -> %s %.1fms", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/", include_in_schema=False)
async def root():
    return {"name": settings.app_name, "version": __version__, "docs": "/docs"}


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": __version__, "ml": runtime.status()}


app.include_router(api_router, prefix="/api/v1")
app.include_router(acp.router, prefix="/acp")  # Agentic Commerce Protocol merchant endpoints

# Representative product photos (Amazon Berkeley Objects, matched by `make photos`). Data, not repo content.
PHOTOS_DIR = settings.processed_dir / "photos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")

# outermost: compresses JSON payloads (search pages, rails, analyses) for every response above 1 kB
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.exception_handler(AcpError)
async def acp_error_handler(_: Request, e: AcpError) -> JSONResponse:
    return JSONResponse(status_code=e.status, content=e.body())
