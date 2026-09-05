import asyncio
import argparse
import sys

from app.config import settings
from app.integrations.razorpay.client import RazorpayClient


async def main(payment_link_id: str) -> None:
    print("RecoverIQ - Verify and Cancel Payment Link")
    print("-------------------------------------------")

    if settings.RAZORPAY_MODE.lower() != "test":
        print("ERROR: RAZORPAY_MODE must be 'test'.")
        sys.exit(1)

    if not settings.RAZORPAY_KEY_ID.startswith("rzp_test_"):
        print(
            "ERROR: Refusing to execute with "
            "a non-Test Mode Razorpay key."
        )
        sys.exit(1)

    client = RazorpayClient()

    print()
    print("1. Fetching Payment Link...")

    before = await client.fetch_payment_link(
        payment_link_id
    )

    print(f"ID: {before.id}")
    print(f"Status: {before.status}")
    print(f"Amount: {before.amount} paise")
    print(f"Currency: {before.currency}")
    print(f"Reference ID: {before.reference_id}")
    print(f"URL: {before.short_url}")

    if before.id != payment_link_id:
        raise RuntimeError(
            "Fetched Payment Link ID does not match."
        )

    if before.currency != "INR":
        raise RuntimeError(
            f"Unexpected currency: {before.currency}"
        )

    print()
    print("2. Cancelling Payment Link...")

    cancelled = await client.cancel_payment_link(
        payment_link_id
    )

    print(f"Status returned: {cancelled.status}")

    print()
    print("3. Fetching again after cancellation...")

    after = await client.fetch_payment_link(
        payment_link_id
    )

    print(f"ID: {after.id}")
    print(f"Status: {after.status}")

    if after.status != "cancelled":
        raise RuntimeError(
            "Payment Link was not confirmed as cancelled."
        )

    print()
    print("SUCCESS")
    print(
        "Payment Link lifecycle verified: "
        "created -> fetched -> cancelled -> fetched."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch and cancel one explicitly supplied Razorpay Test Mode Payment Link."
    )
    parser.add_argument("payment_link_id", help="Test Mode Payment Link ID (plink_...)")
    args = parser.parse_args()
    asyncio.run(main(args.payment_link_id))
