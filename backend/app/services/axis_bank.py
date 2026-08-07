"""
Axis Bank Corporate Banking API Integration
Supports: UPI, NEFT, RTGS, IMPS
Docs: https://developer.axisbank.com/
"""
import httpx
import uuid
import random
from datetime import datetime
from typing import Optional
from app.config import settings


class AxisBankService:
    def __init__(self):
        self.base_url = settings.AXIS_BASE_URL
        self.client_id = settings.AXIS_CLIENT_ID
        self.client_secret = settings.AXIS_CLIENT_SECRET
        self.corporate_id = settings.AXIS_CORPORATE_ID
        self.account_number = settings.AXIS_ACCOUNT_NUMBER
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def _has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret and self.corporate_id)

    def _generate_ref(self) -> str:
        now = datetime.utcnow()
        return f"AXS{now.strftime('%y%m%d')}{uuid.uuid4().hex[:6].upper()}"

    async def _get_token(self) -> str:
        """Obtain OAuth2 token from Axis Bank"""
        if not self._has_credentials():
            return "MOCK_TOKEN"
        if self._access_token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return self._access_token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = datetime.utcnow().replace(
                second=datetime.utcnow().second + int(data.get("expires_in", 3600))
            )
            return self._access_token

    async def get_balance(self) -> dict:
        """Fetch account balance from Axis Bank"""
        if not self._has_credentials():
            # Sandbox/mock response
            balance = round(random.uniform(500000, 2000000), 2)
            return {
                "success": True,
                "account_number": f"{self.account_number[:4]}XXXXXXXX{self.account_number[-2:]}",
                "balance": balance,
                "currency": "INR",
                "last_refreshed": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "mock": True,
            }
        try:
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/corporate/banking/v1/balance",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "corporateId": self.corporate_id,
                        "accountNumber": self.account_number,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "account_number": f"{self.account_number[:4]}XXXXXXXX{self.account_number[-2:]}",
                    "balance": float(data.get("availableBalance", 0)),
                    "currency": "INR",
                    "last_refreshed": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "mock": False,
                }
        except Exception as e:
            return {"success": False, "error": str(e), "balance": 0}

    async def initiate_payment(
        self,
        payment_type: str,
        beneficiary_name: str,
        amount: float,
        beneficiary_account: Optional[str] = None,
        beneficiary_ifsc: Optional[str] = None,
        upi_id: Optional[str] = None,
        remarks: Optional[str] = None,
    ) -> dict:
        """Initiate a payment via Axis Bank API"""
        reference = self._generate_ref()

        if not self._has_credentials():
            # Simulate realistic mock response with slight delay
            import asyncio
            await asyncio.sleep(1.5)
            # 95% success rate in mock mode
            success = random.random() > 0.05
            return {
                "success": success,
                "reference": reference,
                "payment_type": payment_type,
                "amount": amount,
                "beneficiary": beneficiary_name,
                "status": "success" if success else "failed",
                "axis_transaction_id": f"AXIS{uuid.uuid4().hex[:12].upper()}" if success else None,
                "timestamp": datetime.utcnow().isoformat(),
                "mock": True,
                "error": None if success else "Payment failed (mock simulation)",
            }

        try:
            token = await self._get_token()
            payload = {
                "corporateId": self.corporate_id,
                "debitAccountNumber": self.account_number,
                "txnAmount": str(amount),
                "txnCurrency": "INR",
                "remarks": remarks or f"Payment to {beneficiary_name}",
                "uniqueRequestNumber": reference,
            }

            if payment_type in ("NEFT", "RTGS", "IMPS"):
                payload.update({
                    "creditAccountNumber": beneficiary_account,
                    "creditAccountIFSC": beneficiary_ifsc,
                    "beneficiaryName": beneficiary_name,
                    "txnType": payment_type,
                })
                endpoint = f"{self.base_url}/corporate/banking/v1/fund-transfer/{payment_type.lower()}"
            elif payment_type == "UPI":
                payload.update({
                    "upiId": upi_id,
                    "payeeName": beneficiary_name,
                })
                endpoint = f"{self.base_url}/corporate/banking/v1/upi/collect"
            else:
                return {"success": False, "error": f"Unsupported payment type: {payment_type}"}

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "reference": reference,
                    "payment_type": payment_type,
                    "amount": amount,
                    "beneficiary": beneficiary_name,
                    "status": "success",
                    "axis_transaction_id": data.get("transactionId") or data.get("rrn"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "mock": False,
                }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "reference": reference,
                "status": "failed",
                "error": f"Axis Bank API error: {e.response.status_code} {e.response.text[:200]}",
            }
        except Exception as e:
            return {
                "success": False,
                "reference": reference,
                "status": "failed",
                "error": str(e),
            }


axis_bank = AxisBankService()
