import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import router
from app.config import Settings
from app.errors import AppError
from app.repository import MongoBookRepository
from app.seed import build_seed_books
from app.timeutil import iso_now

logger = logging.getLogger("catalog-service")


async def _wait_for_mongo(client, attempts: int = 30, delay_seconds: float = 2.0) -> None:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            await client.admin.command("ping")
            return
        except Exception as exc:
            last_error = exc
            logger.warning("MongoDB is not ready (attempt %s/%s)", attempt, attempts)
            await asyncio.sleep(delay_seconds)
    raise RuntimeError("MongoDB did not become ready") from last_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    from motor.motor_asyncio import AsyncIOMotorClient

    settings: Settings = app.state.settings
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=2000)
    await _wait_for_mongo(client)
    repository = MongoBookRepository(client[settings.mongodb_db])
    await repository.ensure_indexes()
    if await repository.count_books() == 0:
        await repository.insert_many_books(build_seed_books(iso_now()))
        logger.info("Seeded the empty catalog database")
    app.state.repo = repository
    app.state.mongo = client
    logger.info("Catalog service connected to %s", settings.mongodb_db)
    yield
    client.close()


@asynccontextmanager
async def _empty_lifespan(app: FastAPI):
    yield


def create_app(settings: Settings | None = None, repo=None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="BookNest Catalog Service",
        version="1.0.0",
        description=(
            "Owns the book catalogue and the available stock. "
            "The order service reserves and releases stock through this API. "
            "It never reads the order database."
        ),
        lifespan=lifespan if repo is None else _empty_lifespan,
    )
    app.state.settings = settings
    app.state.service_name = settings.service_name
    app.state.mongo = None
    if repo is not None:
        app.state.repo = repo

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        parts = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ()) if part not in ("body",))
            message = error.get("msg", "Invalid value")
            parts.append(f"{location}: {message}" if location else message)
        summary = "; ".join(parts) or "Request validation failed"
        return JSONResponse(status_code=422, content={"error": "VALIDATION_ERROR", "message": summary})
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        response = await call_next(request)
        logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
        return response

    app.include_router(router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
app = create_app()
