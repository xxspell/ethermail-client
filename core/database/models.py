# models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class EtherMailAccount(Base):
    __tablename__ = "ethermail_accounts"

    id = Column(Integer, primary_key=True)
    wallet_address = Column(String, unique=True)
    mnemonic = Column(String)
    private_key = Column(String)
    email = Column(String, nullable=True)
    jwt_token = Column(String)
    proxy = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, default=datetime.utcnow)

    class Config:
        orm_mode = True
