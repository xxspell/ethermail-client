# main.py
import logging

import psutil
import platform
import sys
from datetime import datetime, timedelta
import time
import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database.models import EtherMailAccount
from core.dependencies import verify_api_key
from core.routes.ether import ether_router
from core.schemas import ServiceStatus, ServiceStats, SystemInfo
from fastapi import FastAPI, Depends, HTTPException
from core.database.connect import get_db
from core.logging_config import setup_logging, logger

setup_logging()

START_TIME = datetime.now()
VERSION = "1.0.0"

app = FastAPI(title="EtherMail API",
              description="API для работы с EtherMail",
              version="1.0.0",
              docs_url=settings.docs_url,
              redoc_url=settings.redoc_url,
              openapi_url=settings.openapi_url)
app.include_router(ether_router, prefix="")


@app.get(
    "/status",
    response_model=ServiceStatus,
    summary="Get service status",
    description="Get detailed information about service status, statistics and system information",
    dependencies=[Depends(verify_api_key)]
)
async def get_service_status(db: AsyncSession = Depends(get_db)):
    try:
        total_accounts = await db.execute(
            select(func.count(EtherMailAccount.id))
        )
        total_accounts = total_accounts.scalar()

        current_time = datetime.utcnow()
        active_accounts = await db.execute(
            select(func.count(EtherMailAccount.id)).where(
                EtherMailAccount.last_used >= current_time - timedelta(hours=24)
            )
        )
        active_accounts = active_accounts.scalar()

        accounts_24h = await db.execute(
            select(func.count(EtherMailAccount.id)).where(
                EtherMailAccount.created_at >= current_time - timedelta(hours=24)
            )
        )
        accounts_24h = accounts_24h.scalar()

        cpu_usage = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        dependencies_status = {}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://ethermail.io/", headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"})
                dependencies_status["ethermail_api"] = "ok" if response.status_code == 200 else "error"
        except Exception:
            dependencies_status["ethermail_api"] = "error"

        return ServiceStatus(
            status="ok",
            uptime=str(datetime.now() - START_TIME),
            version=VERSION,
            last_restart=START_TIME,
            stats=ServiceStats(
                total_accounts=total_accounts,
                active_accounts=active_accounts,
                accounts_created_24h=accounts_24h,
            ),
            system_info=SystemInfo(
                python_version=sys.version,
                system=f"{platform.system()} {platform.release()}",
                cpu_usage=cpu_usage,
                memory_usage=memory.percent,
                disk_usage=disk.percent
            ),
            dependencies=dependencies_status
        )

    except Exception as e:
        logger.error(f"Error getting service status: {str(e)}")
