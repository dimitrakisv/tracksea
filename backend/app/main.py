from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.users.router import router as users_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    @app.exception_handler(RequestValidationError)
    async def safe_request_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> Response:
        errors = error.errors()
        if not any("password" in item.get("loc", ()) for item in errors):
            return await request_validation_exception_handler(request, error)

        sanitized_errors = []
        for item in errors:
            sanitized = dict(item)
            if "password" in sanitized.get("loc", ()):
                sanitized.pop("input", None)
            sanitized_errors.append(sanitized)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder({"detail": sanitized_errors}),
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    return app


app = create_app()
