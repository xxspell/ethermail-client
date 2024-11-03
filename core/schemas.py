# schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class CreateSingleAccountRequest(BaseModel):
    proxy: str = Field(..., description="Proxy in format socks5://user:pass@host:port")

class CreateMultipleAccountsRequest(BaseModel):
    proxies: List[str] = Field(..., description="List of proxies, one per line")
    count: int = Field(..., gt=0, description="Number of accounts to create")

class TaskResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")

class AccountResult(BaseModel):
    id: int = Field(..., description="Account ID in database")
    wallet_address: str = Field(..., description="Ethereum wallet address")
    token: str = Field(..., description="JWT token")

class TaskStatusResponse(BaseModel):
    status: str = Field(..., description="Current task status (pending/in_progress/completed/failed)")
    created_at: datetime = Field(..., description="Task creation timestamp")
    total: int = Field(..., description="Total number of accounts to create")
    completed: int = Field(..., description="Number of successfully created accounts")
    failed: int = Field(..., description="Number of failed accounts")
    in_progress: int = Field(..., description="Number of accounts currently being created")
    results: Optional[List[AccountResult]] = Field(None, description="List of created accounts (only when completed)")
    errors: Optional[List[str]] = Field(None, description="List of errors (only when there are failures)")

class AccountResponse(BaseModel):
    id: int
    wallet_address: str
    created_at: datetime
    last_used: datetime
    proxy: Optional[str]
    user_agent: Optional[str]

    class Config:
        orm_mode = True
        from_attributes = True


class EmailMessage(BaseModel):
    id: int = Field(..., description="Message ID")
    from_address: str = Field(..., alias="from", description="Sender address")
    subject: str = Field(..., description="Message subject")
    date: datetime = Field(..., description="Message date")
    html: Optional[List[str]] = Field(None, description="HTML content")
    text: Optional[str] = Field(None, description="Plain text content")

    class Config:
        allow_population_by_field_name = True

class EmailSearchResponse(BaseModel):
    total: int = Field(..., description="Total number of messages found")
    messages: List[EmailMessage] = Field(..., description="List of messages")

class EmailSearchRequest(BaseModel):
    address: str = Field(..., description="Email address to search for")
    subject: Optional[str] = Field(None, description="Filter by subject")
    from_address: Optional[str] = Field(None, description="Filter by sender address")
    date_from: Optional[datetime] = Field(None, description="Filter by date from")
    date_to: Optional[datetime] = Field(None, description="Filter by date to")


class ServiceStats(BaseModel):
    total_accounts: int = Field(..., description="Total number of registered accounts")
    active_accounts: int = Field(..., description="Number of accounts with valid tokens")
    accounts_created_24h: int = Field(..., description="Accounts created in last 24 hours")


class SystemInfo(BaseModel):
    python_version: str = Field(..., description="Python version")
    system: str = Field(..., description="Operating system")
    cpu_usage: float = Field(..., description="CPU usage percentage")
    memory_usage: float = Field(..., description="Memory usage percentage")
    disk_usage: float = Field(..., description="Disk usage percentage")


class ServiceStatus(BaseModel):
    status: str = Field(..., description="Service status (ok/degraded/error)")
    uptime: str = Field(..., description="Service uptime")
    version: str = Field(..., description="Service version")
    last_restart: datetime = Field(..., description="Last service restart time")
    stats: ServiceStats = Field(..., description="Service statistics")
    system_info: SystemInfo = Field(..., description="System information")
    dependencies: Dict[str, str] = Field(..., description="External dependencies status")