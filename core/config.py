from pydantic_settings import BaseSettings
from typing import Annotated, Union



class Settings(BaseSettings):
    API_KEY: str
    API_KEY_NAME: str = "X-API-Key"
    DOCS: Union[str, bool] = False
    REDOC: Union[str, bool] = False
    OPENAPI: Union[str, bool] = False


    class Config:
        env_file = ".env"

    def _convert_to_bool(self, value: Union[str, bool]) -> bool:
        if isinstance(value, str):
            return value.lower() == "true"
        return bool(value)

    @property
    def docs_url(self) -> Union[str, None]:
        if isinstance(self.DOCS, str) and not self._convert_to_bool(self.DOCS):
            return self.DOCS
        return "/docs" if self._convert_to_bool(self.DOCS) else None

    @property
    def redoc_url(self) -> Union[str, None]:
        if isinstance(self.REDOC, str) and not self._convert_to_bool(self.REDOC):
            return self.REDOC
        return "/redoc" if self._convert_to_bool(self.REDOC) else None

    @property
    def openapi_url(self) -> Union[str, None]:
        if isinstance(self.OPENAPI, str) and not self._convert_to_bool(self.OPENAPI):
            return self.OPENAPI
        return "/openapi.json" if self._convert_to_bool(self.OPENAPI) else None


settings = Settings()
