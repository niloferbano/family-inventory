from pydantic import BaseModel


class SMTPSettings(BaseModel):
    host: str = "localhost"
    port: int = 8025

    username: str | None = None
    password: str | None = None

    from_email: str = "notifications@family-inventory.local"

    use_tls: bool = False
    use_ssl: bool = False
