"""
Fake in-memory data for the mock bank teller app.
No real database, no real PII -- just enough to exercise the automation.
"""

MEMBERS = {
    "12345": {
        "member_id": "12345",
        "name": "Jordan Ellis",
        "savings_balance": 4210.55,
        "checking_balance": 1023.10,
    },
    "67890": {
        "member_id": "67890",
        "name": "Priya Nair",
        "savings_balance": 158.00,
        "checking_balance": 42.30,
    },
    "11111": {
        "member_id": "11111",
        "name": "Sam Okafor",
        "savings_balance": 99999.99,
        "checking_balance": 500.00,
    },
}

# A single hardcoded operator login for the mock app.
VALID_USERNAME = "user1"
VALID_PASSWORD = "password123"
