# newkwlab-api-bundle — Python SDK

One API key and one credit balance for the NewKwLab tool suite: email, phone
and card validation, VAT and LEI lookups, sanctions screening, nonprofit and
recall checks, airport data and more — all behind a single gateway.

- **One key** for every connected product (`nkw_live_...`)
- **Credits, not per-API subscriptions** — buy a pack once, spend across tools
- **Not-found results are free** — lookups that come back "no record" cost 0 credits
- **Repeat calls are free for 24h** — same key + same parameters hit the cache, 0 credits
- **Upstream errors are free** — if we fail, you don't pay

## Install

```bash
pip install newkwlab-api-bundle
```

(Requires Python 3.9+. Zero dependencies — standard library only.)

> Status: pre-release. Until the package is published on PyPI, install it from
> this folder (`pip install .`) or copy `src/newkwlab_api_bundle/client.py`
> into your project — it is a single self-contained module.

## Quick start

```python
import os
from newkwlab_api_bundle import NewKwLabClient

client = NewKwLabClient(api_key=os.environ["NKW_API_KEY"])

result = client.email_check("alice@gmail.com")
print(result.data["verdict"], result.data["score"])   # "valid", 100
print(result.credits_charged, result.credits_balance)  # 1, 29999
```

## Getting a key

Keys are issued by activating a license purchased on Gumroad:

```python
from newkwlab_api_bundle import NewKwLabClient

client = NewKwLabClient()
result = client.activate("XXXX-XXXX-XXXX-XXXX", "newkwlab-credits-30000")
print(result["granted_credits"])  # 30000
print(result["api_key"])          # nkw_live_... — shown ONCE, store it now
```

Activating the same license again is safe (no double credit) and returns
`key_already_issued: True` instead of a new key.

## API

| Method | Description |
|---|---|
| `health()` | Gateway health check. No key required. |
| `activate(license_key, product_permalink)` | Activate a Gumroad license → credits (+ first API key, once). |
| `usage()` | Balance, credit lots (source / remaining / expiry), per-product usage. |
| `usage_history(days=30, limit=50, offset=0)` | Ledger history. |
| `create_key(label=None)` | Issue an additional API key (returned once). |
| `disable_key(key_id)` | Disable one of your keys. |
| `call(product, endpoint, method="GET", params=None, body=None)` | Call any connected product. Returns a `CallResult` with `.data`, `.credits_charged`, `.credits_balance`, `.cache`. |
| `email_check(email)` | EmailCheck shortcut (1 credit). |
| `phone_check(phone)` | PhoneCheck shortcut (1 credit). |
| `card_check(number)` | CardCheck shortcut (1 credit). |

Endpoint paths are passed through to the product, e.g.:

```python
client.call("airportbase", "/airport", params={"code": "LAX"})        # 2 credits
client.call("leilookup", "/lei/5493006MFDD84DZ89524")                 # 2 credits, 0 if no record
client.call("vatscope", "/vat", params={"country": "DE", "vat": "123456789"})
```

### Connected products (batch 1)

| Product | Credits | Example endpoint |
|---|---|---|
| emailcheck | 1 | `/validate?email=` |
| phonecheck | 1 | `/validate?phone=` |
| cardcheck | 1 | `/validate?number=` |
| vatscope | 2 | `/vat?country=&vat=` |
| leilookup | 2 | `/lei/{lei}`, `/search?name=` |
| nonprofitcheck | 2 | `/org?ein=`, `/search?q=` |
| sanctionscreen | 2 | see product docs |
| censusaddress | 2 | see product docs |
| recallradar | 2 | see product docs |
| airportbase | 2 | `/airport?code=`, `/search?q=` |

Batch endpoints exist per product (e.g. `/validate/batch`) and are charged per
successful row. More products (GeoIP, VIN, IBAN, SEO score, domain trust,
flight status) are priced and join the same key as they pass the connection gate.

## Errors

Gateway errors raise `GatewayError` with `.status` and `.code`:

```python
from newkwlab_api_bundle import GatewayError, NewKwLabClient

client = NewKwLabClient(api_key="...")
try:
    client.email_check("a@b.com")
except GatewayError as e:
    if e.code == "INSUFFICIENT_CREDITS":
        # top up: buy another credit pack and activate it with the same account flow
        ...
```

If the gateway cannot be reached at all, `GatewayError` is raised with
`status == 0` and `code == "CONNECTION_ERROR"`.

| Code | HTTP | Meaning |
|---|---|---|
| `UNAUTHORIZED` | 401 | Missing or unknown API key |
| `INSUFFICIENT_CREDITS` | 402 | Balance below the product's credit price — nothing was called or charged |
| `UPGRADE_REQUIRED` | 402 | Account canceled and out of credits |
| `CAPABILITY_DENIED` | 403 | Your plan does not include this product or capability (`missing` lists what is needed) |
| `PRODUCT_NOT_FOUND` | 404 | Unknown product id |
| `PRODUCT_NOT_CONNECTED` | 503 | Product is priced but not yet connected to the gateway |
| `RATE_LIMITED` | 429 | Per-key minute limit for your plan reached |
| `UPSTREAM_ERROR` | 502 | The product's upstream failed — not charged |
| `LICENSE_INVALID` | 404 | (activate) License key not found for that product |
| `LICENSE_REFUNDED` | 409 | (activate) License was refunded or the subscription ended |

## Configuration

| Option / env var | Default |
|---|---|
| `api_key` / `NKW_API_KEY` | — |
| `base_url` / `NKW_BASE_URL` | `https://api.newkwlab.com/gateway` |
| `timeout` | 30 seconds |

## Manual live test

```bash
python test_live.py   # health against the production gateway
NKW_BASE_URL=http://127.0.0.1:8899 NKW_API_KEY=nkw_live_... python test_live.py
```

## License

MIT
