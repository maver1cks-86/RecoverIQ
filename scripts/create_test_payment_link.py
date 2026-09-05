import argparse
import asyncio
import sys

from app.config import settings
from app.services.recovery_service import RecoveryService


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create ONE Razorpay Test Mode Payment Link "
            "through RecoverIQ."
        )
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create the Test Mode Payment Link.",
    )

    args = parser.parse_args()

    print("RecoverIQ - Razorpay Test Payment Link")
    print("--------------------------------------")

    # Safety checks
    if settings.RAZORPAY_MODE.lower() != "test":
        print(
            "ERROR: RAZORPAY_MODE must be 'test'."
        )
        sys.exit(1)

    if not settings.RAZORPAY_KEY_ID.startswith(
        "rzp_test_"
    ):
        print(
            "ERROR: Refusing to execute with "
            "a non-Test Mode Razorpay key."
        )
        sys.exit(1)

    if not args.execute:
        print("DRY RUN")
        print()
        print("No Payment Link was created.")
        print()
        print(
            "Run again with --execute to create "
            "exactly one Test Mode Payment Link."
        )
        return

    service = RecoveryService()

    print("Mode: TEST")
    print("Action: PAYMENT_LINK")
    print("Amount: INR 10.00")
    print("Notifications: disabled")
    print()

    result = await service.execute_payment_link(
        original_payment_id="pay_recoveriq_demo_001",
        amount=10.00,
    )

    print("SUCCESS")
    print(f"Provider: {result.provider}")
    print(f"Action: {result.action}")
    print(
        f"Payment Link ID: {result.provider_action_id}"
    )
    print(f"Status: {result.status}")
    print(f"Reference ID: {result.reference_id}")
    print(f"Payment URL: {result.payment_url}")


if __name__ == "__main__":
    asyncio.run(main())