from __future__ import annotations

import os
from enum import StrEnum
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from infrai_client import InfraiClient, InfraiError


class AccountState(StrEnum):
    PENDING_DOMAIN = "pending_domain"
    ACTIVE = "active"


class TenantOnboardingRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_domain: str = Field(min_length=3)
    admin_email: str
    txt_name: str = Field(min_length=1)
    txt_value: str = Field(min_length=1)

    @field_validator("admin_email")
    @classmethod
    def admin_must_belong_to_company(cls, value: str, info: Any) -> str:
        domain = info.data.get("company_domain", "").lower()
        if "@" not in value or value.rsplit("@", 1)[1].lower() != domain:
            raise ValueError("admin_email must belong to company_domain")
        return value


class TenantOnboardingResult(BaseModel):
    tenant_id: str
    company_domain: str
    zone_id: str
    account_state: AccountState
    admin_user: dict[str, Any]


class OnboardingGateway(Protocol):
    def add_domain(self, domain: str, account_id: str) -> dict[str, Any]:
        raise AssertionError("Protocol method called directly")

    def upsert_txt_record(
        self, zone_id: str, name: str, content: str, ttl: int = 300
    ) -> dict[str, Any]:
        raise AssertionError("Protocol method called directly")

    def verify_domain(self, domain: str) -> dict[str, Any]:
        raise AssertionError("Protocol method called directly")

    def get_user_by_email(self, email: str) -> dict[str, Any]:
        raise AssertionError("Protocol method called directly")


def onboard_tenant(
    request: TenantOnboardingRequest, gateway: OnboardingGateway
) -> TenantOnboardingResult:
    domain = gateway.add_domain(request.company_domain, request.tenant_id)
    zone_id = str(domain["zone_id"])
    gateway.upsert_txt_record(zone_id, request.txt_name, request.txt_value)
    verification = gateway.verify_domain(request.company_domain)
    if not verification.get("verified"):
        return TenantOnboardingResult(
            tenant_id=request.tenant_id,
            company_domain=request.company_domain,
            zone_id=zone_id,
            account_state=AccountState.PENDING_DOMAIN,
            admin_user={},
        )
    admin_user = gateway.get_user_by_email(request.admin_email)
    return TenantOnboardingResult(
        tenant_id=request.tenant_id,
        company_domain=request.company_domain,
        zone_id=zone_id,
        account_state=AccountState.ACTIVE,
        admin_user=admin_user,
    )


app = FastAPI(title="Tenant domain onboarding")


@app.post("/tenants/onboard", response_model=TenantOnboardingResult)
def create_tenant(request: TenantOnboardingRequest) -> TenantOnboardingResult:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")

    client = InfraiClient(api_key)
    try:
        return onboard_tenant(request, client)
    except InfraiError as exc:
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "error": exc.details},
        ) from exc
    finally:
        client.close()
