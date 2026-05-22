from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM（OpenAI 兼容接口，完全可配置）
    llm_model: str = "mimo-v2.5"
    llm_api_base_url: str = "https://token-plan-cn.xiaomimimo.com/v1"
    llm_api_key: str = ""
    llm_use_mock: bool = False

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"

    department: str = "心内科"
    room: str = "3号诊室"
    doctor_name: str = "赵主任"


settings = Settings()
