import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Literal, List, Any
from urllib.parse import urlparse

import httpx
import jwt
from eth_account import Account
from httpx import Response, TimeoutException, ConnectError
from mnemonic import Mnemonic
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from web3 import Web3

from core.database.models import EtherMailAccount
from core.logging_config import logger, before_sleep_log_loguru

w3 = Web3()


class ProxyError(Exception):
    pass


class RegistrationError(Exception):
    pass


def _format_proxy(proxy: str, proxy_type: str) -> Dict[str, str]:
    """Formats the proxy into a format understandable for httpx"""
    if not proxy.startswith(('http://', 'https://', 'socks5://')):
        proxy = f"{proxy_type}://{proxy}"

    parsed = urlparse(proxy)

    if proxy_type == "socks5":
        return {
            "http://": f"socks5://{parsed.netloc}",
            "https://": f"socks5://{parsed.netloc}"
        }
    else:
        return {
            "http://": proxy,
            "https://": proxy
        }


class EthermailAPI:
    def __init__(
            self,
            proxy: Optional[str] = None,
            proxy_type: Literal["http", "socks5"] = "socks5",
            user_agent: Optional[str] = None
    ):
        self.headers = {
            'accept': 'application/json',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'cookie': '',
            'origin': 'https://ethermail.io',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://ethermail.io/accounts/login?redirect=%252Fwebmail',
            'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'sec-gpc': '1',
            'user-agent': user_agent if isinstance(user_agent,
                                                   str) else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
        }
        self.base_url = "https://ethermail.io/api"
        self.timeout = httpx.Timeout(30.0)

        if proxy:
            self.proxy = _format_proxy(proxy, proxy_type)
        else:
            self.proxy = None

    async def set_auth_token(self, token: str, account: EtherMailAccount, db: AsyncSession) -> None:
        """Set auth token with expiration check and auto-refresh if needed"""
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            exp_timestamp = decoded.get('exp')

            if not exp_timestamp:
                raise Exception("Invalid token format: no expiration time")


            exp_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            time_left = exp_time - datetime.now(timezone.utc)

            # If there is less than an hour left, update the token
            if time_left.total_seconds() < 3600:
                logger.info("Token expires soon, refreshing...")

                _, nonce = await self.get_nonce(account.wallet_address.lower())

                new_token = await self.register(
                    account.wallet_address.lower(),
                    account.private_key,
                    nonce
                )

                account.jwt_token = new_token
                account.last_used = datetime.utcnow()
                db.add(account)
                await db.commit()

                token = new_token

            self.headers['cookie'] = f"token={token};"

        except Exception as e:
            logger.error(f"Error setting auth token: {str(e)}")
            raise

    def delete_auth_token(self) -> None:
        """Clear the authentication token in cookie headers."""
        self.headers['cookie'] = ''

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=10),
        retry=retry_if_exception_type((TimeoutException, ConnectError, Exception)),
    )
    async def _request(self, method: str, endpoint: str, **kwargs) -> Response:
        url = f"{self.base_url}/{endpoint}"
        logger.debug(f"\nStarting request: {method.upper()} {url} with headers: {self.headers} and proxy: {self.proxy}")
        if 'json' in kwargs:
            logger.debug(f"Request JSON payload: {kwargs['json']}\n")
        if 'params' in kwargs:
            logger.debug(f"Request query parameters: {kwargs['params']}\n")

        try:
            async with httpx.AsyncClient(
                    headers=self.headers,
                    proxies=self.proxy,
                    verify=False,
                    timeout=self.timeout
            ) as client:
                response = await getattr(client, method.lower())(url, **kwargs)
                logger.debug(f"Received response with status code: {response.status_code}")
                response.raise_for_status()

                try:
                    response_json = response.json()
                    logger.debug(f"Response JSON: {response_json}")
                except Exception:
                    logger.error("Response did not contain valid JSON")
                    raise RegistrationError("Invalid JSON response")
                return response

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {str(e)}; Status code: {e.response.status_code}; Response: {e.response.text}")
            raise RegistrationError(f"HTTP {e.response.status_code}: {e.response.text}")
        except (TimeoutException, ConnectError) as e:
            logger.warning(f"Request timed out or connection error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during request: {str(e)}")
            raise e

    async def test_proxy(self) -> bool:
        try:
            async with httpx.AsyncClient(
                    proxies=self.proxy,
                    verify=False,
                    timeout=httpx.Timeout(10.0)
            ) as client:
                response = await client.get("http://ip-api.com/json/")
                response.raise_for_status()
                data = response.json()
                logger.info(f"Proxy info: {data}")
                return True
        except Exception as e:
            logger.info(f"Proxy test failed: {str(e)}")
            return False

    @staticmethod
    async def create_wallet() -> tuple[str, str, str]:
        Account.enable_unaudited_hdwallet_features()
        # Generating a mnemonic phrase
        mnemo = Mnemonic("english")
        mnemonic_phrase = mnemo.generate(strength=128)  # 12 words (128 bits) or 24 words (256 bits)

        # Create a wallet from a mnemonic phrase
        account = Account.from_mnemonic(mnemonic_phrase)

        return account.address, account.key.hex(), mnemonic_phrase

    # @staticmethod
    # async def create_signature(private_key: str, nonce: str) -> str:
    #     account = w3.eth.account.from_key(private_key)
    #     # message_encoded = encode_defunct(text=nonce)
    #
    #     message_bytes = bytes(f"\x19Ethereum Signed Message:\n{len(nonce)}{nonce}", 'utf-8')
    #
    #     signed_message = account.sign_message(message_bytes)
    #     return signed_message.signature.hex()

    @staticmethod
    async def create_signature(private_key: str, message: str) -> str:
        from eth_account import Account
        import eth_utils
        # Convert the message to bytes and add the ethereum signing prefix
        msg_bytes = eth_utils.to_bytes(text=message)
        prefix = "\x19Ethereum Signed Message:\n" + str(len(msg_bytes))
        prefixed_msg = eth_utils.to_bytes(text=prefix) + msg_bytes

        # Create a hash
        msg_hash = eth_utils.keccak(prefixed_msg)

        # Sign
        signed = Account._sign_hash(msg_hash, private_key)

        # Collecting a signature
        signature = eth_utils.to_hex(signed.signature)

        return signature

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2),
        retry=retry_if_exception_type(Exception),
    )
    async def get_nonce(self, address: str):
        try:
            response = await self._request(
                "POST",
                "auth/nonce",
                json={"walletAddress": address}
            )
            result = response.json()
            return result.get('success', False), result.get('nonce', 1)
        except Exception as e:
            logger.error(f"Nonce request failed: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2),
        retry=retry_if_exception_type(Exception),
    )
    async def register(self, address: str, private_key: str, nonce_number: int) -> str:
        try:
            message = f"By signing this message you agree to the Terms and Conditions and Privacy Policy\n\nNONCE: {nonce_number}"

            signature = await self.create_signature(private_key, message)
            response = await self._request(
                "POST",
                "auth/login",
                json={
                    'isMPC': False,
                    'web3Address': address,
                    'signature': signature
                }
            )
            data = response.json()
            if 'token' not in data:
                print(f"Server response: {data}")
                raise RegistrationError("No token in response")
            return data['token']
        except Exception as e:
            logger.error(f"Registration failed: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2),
        retry=retry_if_exception_type(Exception),
    )
    async def get_communities_ids(self, filter_var: str = "show", limit_var: int = 12) -> list[Any]:
        try:
            response = await self._request(
                "GET",
                f"communities?filter={filter_var}&limit={limit_var}",
            )
            data = response.json()
            communities_ids = []
            for community in data:
                communities_ids.append(community.get("tenant_id"))

            return communities_ids
        except Exception as e:
            logger.error(f"Communities failed: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2),
        retry=retry_if_exception_type(Exception),
    )
    async def onboarding(self, communities_ids: List[str], email: str = None) -> str:
        try:

            response = await self._request(
                "POST",
                "users/onboarding",
                json={
                    'communities': communities_ids,
                    'email': email
                }
            )
            data = response.json()
            return data.get('success', False)
        except Exception as e:
            logger.error(f"Registration failed: {str(e)}")
            raise

    async def get_mailboxes(self) -> dict:
        """Get list of mailboxes"""
        response = await self._request("GET", "mailboxes")
        return response.json()

    async def search_messages(self, mailbox_id: str, page: int = 1, limit: int = 10, query: str = "") -> dict:
        """Search messages in mailbox"""
        response = await self._request(
            "POST",
            "messages/search",
            json={
                "next": None,
                "previous": None,
                "page": page,
                "limit": limit,
                "mailbox": mailbox_id,
                "query": query
            }
        )
        return response.json()

    async def get_message_details(self, mailbox_id: str, message_id: int) -> dict:
        """Get detailed message information"""
        response = await self._request(
            "GET",
            f"mailboxes/{mailbox_id}/messages/{message_id}"
        )
        return response.json()

    async def search_emails(
            self,
            subject: Optional[str] = None,
            from_address: Optional[str] = None,
            date_from: Optional[datetime] = None,
            date_to: Optional[datetime] = None
    ) -> List[dict]:
        try:
            """Search emails with filters"""
            mailboxes = await self.get_mailboxes()

            inbox = next(
                (box for box in mailboxes["results"] if box["name"] == "INBOX"),
                None
            )

            if not inbox:
                raise Exception("Inbox not found")

            messages = await self.search_messages(
                inbox["id"],
                query=subject if subject else ""
            )

            detailed_messages = []
            for msg in messages["results"]:
                if from_address and msg["from"]["address"] != from_address:
                    continue

                if date_from and datetime.fromisoformat(msg["date"]) < date_from:
                    continue

                if date_to and datetime.fromisoformat(msg["date"]) > date_to:
                    continue

                message_data = await self.get_message_details(inbox["id"], msg["id"])

                detailed_messages.append({
                    "id": message_data["id"],
                    "from": message_data["from"]["address"],
                    "subject": message_data["subject"],
                    "date": message_data["date"],
                    "html": message_data.get("html", []),
                    "text": message_data.get("text", "")
                })

            return detailed_messages
        except Exception as e:
            logger.error(f"Error with search emails messages: {e}")
            raise e
