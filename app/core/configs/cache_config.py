from pydantic import computed_field
from pydantic_settings import BaseSettings


class CacheConfiguration(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    username: str | None = None
    password: str | None = None
    timeout: int = 20

    @computed_field
    @property
    def url(self) -> str:
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        elif self.password:
            auth = f":{self.password}@"

        return f"redis://{auth}{self.host}:{self.port}/{self.db}"
