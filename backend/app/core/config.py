from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    app_name: str = "SmartSearch API"

    database_url: str = "postgresql+asyncpg://smartsearch:smartsearch@localhost:5435/smartsearch"
    redis_url: str = "redis://localhost:6379/0"
    mlflow_tracking_uri: str = "http://localhost:5001"

    admin_api_key: str = "dev-admin-key"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    public_web_url: str = "http://localhost:3000"  # storefront URL used in ACP order permalinks

    # LLM (AI Shopping Agent + attribute enrichment). Without a key the agent falls back to rule-based search.
    anthropic_api_key: str | None = None
    agent_model: str = "claude-sonnet-5-5"  # conversational agent
    bulk_model: str = "claude-haiku-5-5"  # batch jobs: graph community summaries, attribute enrichment
    agent_effort: str = "low"  # chat latency matters more than depth here

    # Microsoft-Decision-1 (typed decision scoring). backend: auto | openrouter | foundry | local
    decision_backend: str = "auto"
    openrouter_api_key: str | None = None
    decision1_endpoint: str | None = None  # Foundry resource endpoint
    decision1_deployment: str = "Microsoft-Decision-1"
    decision1_api_key: str | None = None
    decision_model: str = "microsoft/microsoft-decision-1"
    decision_intent_threshold: float = 0.5

    # Static embeddings (model2vec): CPU-only, no torch/onnxruntime, portable to x86 macOS and slim containers.
    embedding_model: str = "minishlab/potion-retrieval-32M"
    embedding_dim: int = 512

    # Product imagery (Higgsfield REST API, https://cloud.higgsfield.ai). WANDS ships no photos; `make images` generates
    # them for the most-shown products. Without keys the script prints the prompts and the storefront keeps category tiles.
    hf_api_key_id: str | None = None
    hf_api_key_secret: str | None = None
    image_model: str = "qwen"  # qwen | soul | z-image (see app/imagery.py)
    images_dir: Path = REPO_ROOT / "frontend" / "public" / "img" / "products"

    # Agentic Commerce Protocol (merchant endpoints under /acp); the payment side is a labelled mock
    acp_api_key: str = "dev-acp-key"
    acp_merchant_id: str = "smartsearch-demo"
    acp_webhook_url: str | None = None
    acp_webhook_secret: str = "dev-acp-webhook-secret"

    data_dir: Path = REPO_ROOT / "data"

    # Ranking / retrieval knobs
    retrieval_top_k: int = 200
    results_page_size: int = 24

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.raw_dir, s.processed_dir, s.artifacts_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
