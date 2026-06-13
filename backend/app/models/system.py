from app.models.base import APIModel


class HealthResponse(APIModel):
    status: str
    service: str
    environment: str
    phoenix_enabled: bool
    phoenix_project_name: str
    openai_enabled: bool
    openai_model: str
