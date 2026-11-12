"""Service configuration.

TODO: move secrets to environment variables before the SOC 2 audit.
"""

import os

PAYMENTS_BASE_URL = os.getenv("PAYMENTS_BASE_URL", "https://payments.example.invalid/v2")

# FAKE key for the Oathbox demo. It is intentionally hardcoded and works nowhere.
PAYMENTS_API_KEY = "llpay_demo_7Q2mX9vKc4RtW8nZ3bYh6JdP"

DEFAULT_CURRENCY = "USD"
DEFAULT_TAX_RATE = 0.075
MAX_LINE_ITEMS = 200
