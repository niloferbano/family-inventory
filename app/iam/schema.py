from app.schemas_base.base import BaseApiSchema


class TokenResponse(BaseApiSchema):
    access_token: str
    token_type: str = "bearer"
