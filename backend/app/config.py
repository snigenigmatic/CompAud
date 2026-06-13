from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]

PS3_DATA_DIR = REPO_ROOT / "Problem_03_Compliance_Evidence" / "sample_data"
PS3_POLICY_DOCUMENTS_PATH = PS3_DATA_DIR / "policy_documents.txt"
PS3_EVIDENCE_CSV_PATH = PS3_DATA_DIR / "evidence_artifacts.csv"


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    phoenix_enabled: bool = Field(default=True, alias="PHOENIX_ENABLED")
    phoenix_project_name: str = Field(
        default="rakshak-ai-backend",
        alias="PHOENIX_PROJECT_NAME",
    )
    phoenix_collector_endpoint: str = Field(
        default="http://localhost:4317",
        alias="PHOENIX_COLLECTOR_ENDPOINT",
    )

    openai_enabled: bool = Field(default=False, alias="OPENAI_ENABLED")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.2", alias="OPENAI_MODEL")
    openai_reasoning_effort: str = Field(default="low", alias="OPENAI_REASONING_EFFORT")

    neo4j_uri: str = Field(default="", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")

    # --- PS3: Automated Compliance Evidence Collection & Audit ---
    embedding_model_name: str = Field(
        default="BAAI/bge-small-en-v1.5", alias="PS3_EMBEDDING_MODEL"
    )
    embedding_device: str = Field(default="cpu", alias="PS3_EMBEDDING_DEVICE")
    link_similarity_threshold: float = Field(default=0.42, alias="PS3_LINK_THRESHOLD")
    framework_match_bonus: float = Field(default=0.05, alias="PS3_FRAMEWORK_BONUS")
    freshness_default_sla_days: int = Field(default=90, alias="PS3_FRESHNESS_DEFAULT_SLA")
    confidence_floor: float = Field(default=0.7, alias="PS3_CONFIDENCE_FLOOR")
    ps3_llm_normalize_requirements: bool = Field(default=False, alias="PS3_LLM_NORMALIZE")
    ps3_llm_narratives: bool = Field(default=True, alias="PS3_LLM_NARRATIVES")
    ps3_policy_documents_path: str = Field(default="", alias="PS3_POLICY_DOCUMENTS_PATH")
    ps3_evidence_csv_path: str = Field(default="", alias="PS3_EVIDENCE_CSV_PATH")

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
