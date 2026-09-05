from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


SEED = 42

ROOT = Path(__file__).resolve().parents[1]

INPUT = (
    ROOT
    / "data"
    / "generated"
    / "recovery_events.csv"
)

OUTPUT = (
    ROOT
    / "data"
    / "processed"
)


def main():

    df = pd.read_csv(INPUT)

    train_val, test = train_test_split(
        df,
        test_size=0.20,
        random_state=SEED,
        stratify=df["recovered"],
    )

    train, validation = train_test_split(
        train_val,
        test_size=0.20,
        random_state=SEED,
        stratify=train_val["recovered"],
    )

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    train.to_csv(
        OUTPUT / "train.csv",
        index=False,
    )

    validation.to_csv(
        OUTPUT / "validation.csv",
        index=False,
    )

    test.to_csv(
        OUTPUT / "test.csv",
        index=False,
    )

    print(
        "Train:",
        train.shape
    )

    print(
        "Validation:",
        validation.shape
    )

    print(
        "Test:",
        test.shape
    )


if __name__ == "__main__":
    main()