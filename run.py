import uvicorn

from core.logging_config import get_uvicorn_log_config

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_config=get_uvicorn_log_config()
    )