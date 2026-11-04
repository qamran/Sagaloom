import json
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent.parent
# Later files override earlier ones: api/.env beats the project-root .env.
_ENV_FILES = (str(_API_DIR.parent / ".env"), str(_API_DIR / ".env"))


ALLOWED_MODELS_FILE = Path(__file__).resolve().parent / "allowed_models.json"


class AllowedModel(BaseModel):
    id: str
    price_in: float  # USD per 1M input tokens
    price_out: float  # USD per 1M output tokens


def load_allowed_models(path: Path = ALLOWED_MODELS_FILE) -> list[AllowedModel]:
    """The account's guardrail-allowed OpenRouter models that support tools and structured output
    (R11.G10)."""
    return [AllowedModel(**m) for m in json.loads(path.read_text(encoding="utf-8"))]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    openrouter_api_key: SecretStr
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    gemini_api_key: SecretStr | None = None
    chat_model: str = "openai/gpt-6-luna"
    judge_model: str = "openai/gpt-6-luna"
    extractor_model: str = "openai/gpt-6-luna"
    guard_model: str = "openai/gpt-6-luna"
    provider_order: list[str] = ["openai"]
    embed_model: str = "openai/text-embedding-3-small"
    api_shared_secret: SecretStr
    web_origin: str = "http://localhost:3000"
    data_dir: Path = Path("data")
    price_in_per_mtok: float = 0.10
    price_out_per_mtok: float = 0.50
    allowed_models: list[AllowedModel] = Field(default_factory=load_allowed_models)
