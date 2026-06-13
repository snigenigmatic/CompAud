from app.models.base import APIModel


class ApiErrorDetail(APIModel):
    code: str
    message: str


class ErrorResponse(APIModel):
    error: ApiErrorDetail
