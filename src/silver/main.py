"""Silver entrypoint.

    python -m silver.main \
      --bronze-uri ./data/bronze/orders_raw \
      --silver-uri ./data/silver/orders
"""

from __future__ import annotations

import argparse

from silver.transform import run_bronze_to_silver


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bronze-uri", required=True)
    parser.add_argument("--silver-uri", required=True)
    args = parser.parse_args(argv)

    row_count = run_bronze_to_silver(args.bronze_uri, args.silver_uri)
    print(f"wrote {row_count} rows to {args.silver_uri}")


if __name__ == "__main__":
    main()
