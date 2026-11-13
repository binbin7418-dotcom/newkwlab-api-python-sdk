"""Manual live test for the Python SDK (not part of the package).

Usage:
    python test_live.py                     -> health against the production gateway
    NKW_BASE_URL=http://127.0.0.1:8899 NKW_API_KEY=nkw_live_... python test_live.py

When NKW_API_KEY is set, also runs usage + one CardCheck call (1 credit;
the second identical call must come back as a 0-credit cache HIT) and a
forged-key rejection check.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from newkwlab_api_bundle import GatewayError, NewKwLabClient

client = NewKwLabClient()
print("baseUrl:", client.base_url)
print("health:", client.health())

if os.environ.get("NKW_API_KEY"):
    usage = client.usage()
    print("usage.balance:", usage["balance"], "plan:", usage["plan_id"])

    r1 = client.card_check("4242424242424242")
    print("cardcheck #1:", r1.data["network"], "valid:", r1.data["valid"],
          "| charged:", r1.credits_charged, "balance:", r1.credits_balance,
          "cache:", r1.cache)

    r2 = client.card_check("4242424242424242")
    print("cardcheck #2:", "| charged:", r2.credits_charged, "cache:", r2.cache)

    try:
        bad = NewKwLabClient(api_key="nkw_live_forged000000000000000000000000000000")
        bad.usage()
        print("ERROR: forged key was accepted")
        sys.exit(1)
    except GatewayError as e:
        print("forged key rejected:", isinstance(e, GatewayError), e.status, e.code)

print("SDK TEST DONE")
