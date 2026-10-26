import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging import configure_logging
from app.routers import health


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Charla API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    structlog.get_logger().info("app_created", env=settings.env)
    return app


app = create_app()
