import asyncio
from datetime import datetime
from typing import List
from fastapi import APIRouter
from fake_useragent import UserAgent
from fastapi import FastAPI, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api_client import EthermailAPI
from core.database.connect import get_db
from core.database.models import EtherMailAccount
from core.dependencies import verify_api_key
from core.schemas import TaskResponse, CreateMultipleAccountsRequest, CreateSingleAccountRequest, TaskStatusResponse, \
    AccountResponse, EmailSearchResponse, EmailSearchRequest

from core.task_manager import TaskManager, TaskStatus


task_manager = TaskManager()
ETHERMAIL_DOMAIN = "ethermail.io"
ether_router = APIRouter()

async def register_account(proxy: str, db: AsyncSession):
    try:
        ua = UserAgent()
        user_agent = ua.random
        api_client = EthermailAPI(proxy=proxy, user_agent=user_agent)

        address, private_key, mnemonic = await api_client.create_wallet()

        _, nonce = await api_client.get_nonce(address.lower())

        token = await api_client.register(address.lower(), private_key, nonce)

        communities_ids = await api_client.get_communities_ids()

        if not await api_client.onboarding(communities_ids=communities_ids):
            logger.info("Error onboarding")

        logger.info("Register suc")

        account = EtherMailAccount(
            wallet_address=address,
            private_key=private_key,
            mnemonic=mnemonic,
            jwt_token=token,
            email=f"{address}@{ETHERMAIL_DOMAIN}",
            proxy=proxy,
            user_agent=user_agent,
            last_used=datetime.utcnow()
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)

        return {
            "id": account.id,
            "wallet_address": address,
            "token": token
        }
    except Exception as e:
        logger.error(f"Error registering account: {str(e)}")
        raise


async def process_registration_task(task_id: str, db: AsyncSession):
    task = task_manager.get_task(task_id)
    if not task:
        return

    task.status = TaskStatus.IN_PROGRESS

    async def register_with_proxy(proxy: str):
        try:
            result = await register_account(proxy, db)
            task.completed_count += 1
            task.results.append(result)
        except Exception as e:
            task.failed_count += 1
            task.errors.append(str(e))

    tasks = []
    for i in range(task.count):
        if i < len(task.proxies):
            tasks.append(register_with_proxy(task.proxies[i]))

    await asyncio.gather(*tasks)
    task.status = TaskStatus.COMPLETED


@ether_router.post(
    "/create_accounts",
    response_model=TaskResponse,
    summary="Create multiple accounts",
    description="Start a task to create multiple EtherMail accounts using provided proxies",
    dependencies=[Depends(verify_api_key)]
)
async def create_accounts(
        request: CreateMultipleAccountsRequest,
        db: AsyncSession = Depends(get_db)
):
    if not request.proxies:
        raise HTTPException(status_code=400, detail="No proxies provided")

    if request.count > len(request.proxies):
        raise HTTPException(status_code=400, detail="Not enough proxies for requested account count")

    task_id = task_manager.create_task(request.proxies, request.count)
    asyncio.create_task(process_registration_task(task_id, db))

    return TaskResponse(task_id=task_id)


@ether_router.post(
    "/create_account",
    response_model=TaskResponse,
    summary="Create single account",
    description="Start a task to create a single EtherMail account using provided proxy",
    dependencies=[Depends(verify_api_key)]
)
async def create_account(
        request: CreateSingleAccountRequest,
        db: AsyncSession = Depends(get_db)
):
    task_id = task_manager.create_task([request.proxy], 1)
    asyncio.create_task(process_registration_task(task_id, db))
    return TaskResponse(task_id=task_id)


@ether_router.get(
    "/task/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get task status",
    description="Get current status and results of the registration task",
    dependencies=[Depends(verify_api_key)]
)
async def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatusResponse(
        status=task.status.value,
        created_at=task.created_at,
        total=task.count,
        completed=task.completed_count,
        failed=task.failed_count,
        in_progress=task.count - (task.completed_count + task.failed_count),
        results=task.results if task.status == TaskStatus.COMPLETED else None,
        errors=task.errors if task.errors else None
    )


@ether_router.get(
    "/accounts",
    response_model=List[AccountResponse],
    summary="Get all accounts",
    description="Get list of all registered accounts",
    dependencies=[Depends(verify_api_key)]
)
async def get_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EtherMailAccount))
    accounts = result.scalars().all()
    return [AccountResponse.from_orm(acc) for acc in accounts]


@ether_router.get(
    "/account/{account_id}",
    response_model=AccountResponse,
    summary="Get account details",
    description="Get detailed information about specific account",
    dependencies=[Depends(verify_api_key)]
)
async def get_account(account_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EtherMailAccount).filter(EtherMailAccount.id == account_id)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return AccountResponse.from_orm(account)


@ether_router.get(
    "/emails",
    response_model=EmailSearchResponse,
    summary="Get email messages",
    description="Search and retrieve emails for specific address with optional filters",
    dependencies=[Depends(verify_api_key)]
)
async def get_emails(
        request: EmailSearchRequest,
        db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(
            select(EtherMailAccount).filter(EtherMailAccount.email == request.address)
        )
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        api_client = EthermailAPI(
            proxy=account.proxy,
            user_agent=account.user_agent
        )

        await api_client.set_auth_token(account.jwt_token, account, db)

        messages = await api_client.search_emails(
            subject=request.subject,
            from_address=request.from_address,
            date_from=request.date_from,
            date_to=request.date_to
        )

        return EmailSearchResponse(
            total=len(messages),
            messages=messages
        )

    except Exception as e:
        logger.error(f"Error getting emails: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
