from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent.parent
# Later files override earlier ones: api/.env beats the project-root .env.
_ENV_FILES = (str(_API_DIR.parent / ".env"), str(_API_DIR / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    gemini_api_key: str | None = None
    chat_model: str = "openai/gpt-6-luna"
    judge_model: str = "openai/gpt-6-luna"
    extractor_model: str = "openai/gpt-6-luna"
    guard_model: str = "openai/gpt-6-luna"
    provider_order: list[str] = ["openai"]
    embed_model: str = "openai/text-embedding-3-small"
    api_shared_secret: str
    web_origin: str = "http://localhost:3000"
    data_dir: Path = Path("data")
    price_in_per_mtok: float = 0.10
    price_out_per_mtok: float = 0.50
