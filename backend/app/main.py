from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import live, meta, rfqs
from app.config import settings
from app.errors import AppError

app = FastAPI(title="RFQ British Auctions", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    body = {"detail": exc.message, "code": exc.code}
    if exc.field:
        body["errors"] = {exc.field: exc.message}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Flatten Pydantic's errors into {field: message} so forms can show them inline."""
    errors: dict[str, str] = {}
    for error in exc.errors():
        location = [str(part) for part in error["loc"] if part != "body"]
        field = location[0] if location else "_"
        errors.setdefault(field, error["msg"].removeprefix("Value error, "))
    return JSONResponse(
        status_code=422,
        content={"detail": "Some fields need fixing", "code": "VALIDATION_ERROR", "errors": errors},
    )


app.include_router(meta.router)
app.include_router(rfqs.router)
app.include_router(live.router)
