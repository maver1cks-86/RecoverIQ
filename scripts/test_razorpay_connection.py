import sys

import httpx

from app.config import settings


def main() -> None:
    print("RecoverIQ Razorpay connection check")
    print("-----------------------------------")

    if settings.RAZORPAY_MODE.lower() != "test":
        print(
            "ERROR: RAZORPAY_MODE must be 'test'."
        )
        sys.exit(1)

    if not settings.RAZORPAY_KEY_ID:
        print(
            "ERROR: RAZORPAY_KEY_ID is not configured."
        )
        sys.exit(1)

    if not settings.RAZORPAY_KEY_SECRET:
        print(
            "ERROR: RAZORPAY_KEY_SECRET is not configured."
        )
        sys.exit(1)

    if not settings.RAZORPAY_KEY_ID.startswith(
        "rzp_test_"
    ):
        print(
            "ERROR: Refusing to run because the "
            "configured Razorpay key is not a Test Mode key."
        )
        sys.exit(1)

    print("Mode: test")
    print("Key type: Test Mode")
    print("Operation: READ ONLY")
    print()

    try:
        response = httpx.get(
            f"{settings.RAZORPAY_BASE_URL}/payment_links",
            auth=(
                settings.RAZORPAY_KEY_ID,
                settings.RAZORPAY_KEY_SECRET,
            ),
            params={
                "count": 1,
            },
            timeout=10.0,
        )

    except httpx.TimeoutException:
        print(
            "ERROR: Razorpay request timed out."
        )
        sys.exit(1)

    except httpx.RequestError as exc:
        print(
            "ERROR: Could not connect to Razorpay."
        )
        print(
            f"Reason: {exc.__class__.__name__}"
        )
        sys.exit(1)

    if response.status_code in (401, 403):
        print(
            "ERROR: Razorpay authentication failed."
        )
        print(
            f"HTTP {response.status_code}"
        )
        sys.exit(1)

    if response.status_code == 429:
        print(
            "ERROR: Razorpay rate limit reached."
        )
        sys.exit(1)

    if not response.is_success:
        print(
            "ERROR: Razorpay returned an unexpected response."
        )
        print(
            f"HTTP {response.status_code}"
        )

        try:
            data = response.json()

            error = data.get("error", {})

            if isinstance(error, dict):
                description = error.get(
                    "description"
                )

                if description:
                    print(
                        f"Message: {description}"
                    )

        except ValueError:
            pass

        sys.exit(1)

    print(
        "SUCCESS: Authenticated with Razorpay Test Mode."
    )
    print(
        f"HTTP {response.status_code}"
    )
    print(
        "Read-only Payment Links endpoint is accessible."
    )


if __name__ == "__main__":
    main()