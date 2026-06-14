from fastapi import Request
from fastapi.responses import JSONResponse

from pydantic import BaseModel

class ErrorResponse(BaseModel):
    error: dict
class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    response = ErrorResponse(
        error={
            "code": exc.code,
            "message": exc.message,
        }
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )
