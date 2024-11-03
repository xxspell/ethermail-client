
from fastapi import Security, HTTPException, Depends
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
from core.logging_config import logger
from core.config import settings

api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key:
        logger.warning("No API key provided")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="No API key provided"
        )

    if api_key != settings.API_KEY:
        logger.warning(f"Invalid API key provided: {api_key}")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )

    return api_key

