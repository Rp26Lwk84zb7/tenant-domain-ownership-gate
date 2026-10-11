from typing import Any

from tenant_onboarding import AccountState, TenantOnboardingRequest, onboard_tenant


class RecordingGateway:
    def __init__(self, verified: bool = True) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.verified = verified

    def add_domain(self, domain: str, account_id: str) -> dict[str, Any]:
        self.calls.append(("add_domain", domain, account_id))
        return {"zone_id": "zone_acme"}

    def upsert_txt_record(
        self, zone_id: str, name: str, content: str, ttl: int = 300
    ) -> dict[str, Any]:
        self.calls.append(("upsert_txt_record", zone_id, name, content, ttl))
        return {"record_id": "record_proof"}

    def verify_domain(self, domain: str) -> dict[str, Any]:
        self.calls.append(("verify_domain", domain))
        return {"verified": self.verified}

    def get_user_by_email(self, email: str) -> dict[str, Any]:
        self.calls.append(("get_user_by_email", email))
        return {"id": "user_42", "email": email}


def test_verified_domain_activates_tenant_and_resolves_admin() -> None:
    gateway = RecordingGateway()
    request = TenantOnboardingRequest(
        tenant_id="tenant_acme",
        company_domain="acme.example",
        admin_email="owner@acme.example",
        txt_name="_infrai-proof",
        txt_value="tenant-proof-123",
    )

    result = onboard_tenant(request, gateway)

    assert result.account_state is AccountState.ACTIVE
    assert result.zone_id == "zone_acme"
    assert result.admin_user["id"] == "user_42"
    assert gateway.calls == [
        ("add_domain", "acme.example", "tenant_acme"),
        ("upsert_txt_record", "zone_acme", "_infrai-proof", "tenant-proof-123", 300),
        ("verify_domain", "acme.example"),
        ("get_user_by_email", "owner@acme.example"),
    ]


def test_unverified_domain_stays_pending_without_admin_lookup() -> None:
    gateway = RecordingGateway(verified=False)
    request = TenantOnboardingRequest(
        tenant_id="tenant_acme",
        company_domain="acme.example",
        admin_email="owner@acme.example",
        txt_name="_infrai-proof",
        txt_value="tenant-proof-123",
    )

    result = onboard_tenant(request, gateway)

    assert result.account_state is AccountState.PENDING_DOMAIN
    assert result.admin_user == {}
    assert [call[0] for call in gateway.calls] == [
        "add_domain", "upsert_txt_record", "verify_domain"
    ]
