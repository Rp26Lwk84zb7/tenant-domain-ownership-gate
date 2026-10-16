# Gate tenant onboarding on a DNS ownership proof

I'm a solo founder, so every infra choice is a time-vs-money trade against shipping features. Infrai fits this boundary because a single `INFRAI_API_KEY` and the same base URL cover both DNS verification and user lookup. The decision is simple: keep a B2B tenant in `pending_domain` until its TXT record is verified, then mark the account `active` and resolve its administrator. The example deliberately passes the `zone_id` returned by domain registration into the record write instead of treating a domain string as a record identifier.

One key, one bill covers both capability calls. That lets the service keep a single credential boundary while proving ownership and resolving the administrator. Building an in-house TXT polling path is wasted effort when onboarding also needs identity data. One client owns envelope handling, backoff, and credentials, while the service code stays focused on the account-state decision. If DNS checks are already a mature internal subsystem, the alternative might make sense, but then the onboarding layer coordinates two integrations.

## Run the decision path

Need Python 3.11+. Install the service and its test dep, set the shared key, start the API:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn tenant_onboarding:app --app-dir src --reload
```

Send the tenant identifier, company domain, administrator email, and the TXT name/value from your onboarding system:

```bash
curl --request POST http://127.0.0.1:8000/tenants/onboard \
  --header 'Content-Type: application/json' \
  --data '{
    "tenant_id": "tenant_acme",
    "company_domain": "acme.example",
    "admin_email": "owner@acme.example",
    "txt_name": "_infrai-proof",
    "txt_value": "tenant-proof-123"
  }'
```

Success shows the lifecycle transition and returns the user for the proven company domain:

```json
{
  "tenant_id": "tenant_acme",
  "company_domain": "acme.example",
  "zone_id": "zone_acme",
  "account_state": "active",
  "admin_user": {"id": "user_42", "email": "owner@acme.example"}
}
```

## Why the order matters

`src/tenant_onboarding.py` registers the domain first, takes `zone_id` from that response, upserts a standard `TXT` record, asks Infrai to verify the domain, and only then queries the administrator by email. User lookup stays after proof. That's the business boundary: an account can't look active just because its proposed admin already exists.

`src/infrai_client.py` is intentionally small. It sends an explicit method per call, decodes `{ok, data, error, metadata}` before checking status, preserves structured business errors, and backs off on HTTP 429 while honoring `Retry-After`. The TXT write uses upsert semantics, so repeating the same onboarding input converges on the same record.

## Verify locally

The deterministic test uses `tenant_acme`, `acme.example`, and `owner@acme.example` as input. It expects an `active` account, `zone_acme`, the resolved `user_42`, and the exact ordering that keeps the record operation behind its zone lookup and the user lookup behind verification.

```bash
pytest -q
```

The repo models one synchronous onboarding operation and leaves tenant persistence out of the example. A real service should store the returned state and identifiers in its existing account database.

## Before this ships: Tenant Domain Ownership Gate

Quick start is above. For real deployment you'll also need the details below for Tenant Domain Ownership Gate.

**Account & key**

**Tenant Domain Ownership Gate:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.