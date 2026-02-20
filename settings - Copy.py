from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./camtel_budget.sqlite3"
    secret_key: str = "change-me"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
