from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.v1 import assets, auth, conversations, memories, operations, personas, runs
from app.config import settings
from app.db import engine, fetch_one, transaction
from app.errors import AppError
from app.services.body_limit import UploadBodyLimit


@asynccontextmanager
async def lifespan(app):
    yield
    await engine.dispose()


app = FastAPI(title="AI 陪伴 Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(UploadBodyLimit)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "X-Request-ID"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    try:
        request.state.request_id = str(UUID(request.headers.get("X-Request-ID", "")))
    except (ValueError, TypeError):
        request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path != "/v1/health/live" and "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


def error_response(request, status, code, message):
    return JSONResponse({"error": {"code": code, "message": message,
                         "request_id": getattr(request.state, "request_id", str(uuid4()))}}, status_code=status)


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    return error_response(request, exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return error_response(request, 422, "VALIDATION_ERROR", "请求格式或字段不符合要求。")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_response(request, exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
                          "资源不存在。" if exc.status_code == 404 else "请求无法处理。")


@app.exception_handler(IntegrityError)
async def conflict_error(request: Request, exc: IntegrityError):
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
    if constraint == "uq_one_active_run_per_conversation":
        return error_response(request, 409, "RUN_ACTIVE", "当前回复还在生成，请等待或停止。")
    if "client_message_id" in constraint:
        return error_response(request, 409, "IDEMPOTENCY_CONFLICT", "发送标识已用于其他请求。")
    return error_response(request, 409, "CONFLICT", "资料已变化，请刷新后重试。")


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return error_response(request, 503, "DATABASE_UNAVAILABLE", "服务暂时不可用，请稍后重试。")


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Avoid logging raw exceptions carrying SQL parameter values or upstream personal content.
    return error_response(request, 500, "INTERNAL_ERROR", "服务暂时无法处理，请稍后重试。")


@app.get("/v1/health/live", tags=["health"])
async def live():
    return {"status": "ok", "provider_mode": settings.provider_mode}


@app.get("/v1/health/ready", tags=["health"])
async def ready():
    try:
        async with transaction() as conn:
            await fetch_one(conn, "SELECT id FROM jobs LIMIT 1")
            extension = await fetch_one(conn, "SELECT extversion FROM pg_extension WHERE extname='vector'")
            if not extension:
                raise AppError(503, "NOT_READY", "数据库向量扩展尚未准备完成。")
    except SQLAlchemyError:
        raise AppError(503, "NOT_READY", "数据库尚未准备完成，请先运行迁移。") from None
    return {"status": "ready", "database": "ok", "vector": "ok", "queue": "postgresql"}


for router in (auth.router, assets.router, personas.router, conversations.router, runs.router,
               memories.router, operations.router):
    app.include_router(router, prefix="/v1")


def serve():
    """Local entry point; psycopg requires the selector event loop on Windows."""
    import asyncio
    import sys

    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host=settings.api_host, port=settings.api_port))
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    serve()
