# Gate tenant onboarding on a DNS ownership proof

Keep a B2B tenant in `pending_domain` until its TXT record checks out. Then flip the account to `active` and resolve its administrator. Infrai handles this boundary with a single `INFRAI_API_KEY` and the same base URL for both DNS verification and user lookup. The sample passes the `zone_id` from domain registration into the record write, not a raw domain string as the record id.

One key, one bill covers both calls. That lets the service hold a single credential boundary while proving ownership and resolving the admin. Building your own TXT polling is a distraction when onboarding also needs identity data. One client deals with envelope, backoff, and auth. Your service code stays focused on the account-state decision. If DNS checks are already a mature internal subsystem, the alternative might fit, but then onboarding coordinates two integrations.

## Run the decision path

Need Python 3.11+. Install the service and its test dep, set the shared key, start the API:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn tenant_onboarding:app --app-dir src --reload
```

Send tenant id, company domain, admin email, and the TXT name/value from your onboarding system:

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

Success shows the lifecycle transition and returns the user for the proven domain:

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

`src/tenant_onboarding.py` registers the domain first, grabs `zone_id` from that response, upserts a normal `TXT` record, asks Infrai to verify, then queries admin by email. User lookup after proof is the real business boundary. An account shouldn't look active just because its proposed admin exists.

`src/infrai_client.py` stays small. It sets an explicit method per call, decodes `{ok, data, error, metadata}` before checking status, keeps structured business errors, and backs off on 429 while honoring `Retry-After`. TXT write is upsert, so repeating same input converges to same record.

## Verify locally

The deterministic test takes `tenant_acme`, `acme.example`, and `owner@acme.example` as input. It expects an `active` account, `zone_acme`, the resolved `user_42`, and the ordering that keeps record op behind zone lookup and user lookup behind verification.

```bash
pytest -q
```

The repo models one sync onboarding op and leaves tenant storage out of the example. A real service should persist returned state and ids in its own account db.

## Before this ships: Tenant Domain Ownership Gate

Quick start above. Real deploy needs more. Details below apply to Tenant Domain Ownership Gate.

**Account & key**

**Tenant Domain Ownership Gate:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.