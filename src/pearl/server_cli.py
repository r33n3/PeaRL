"""CLI entry point for the PeaRL API server."""

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pearl-server",
        description="PeaRL API server — Policy-enforced Autonomous Risk Layer",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Local dev mode: SQLite database, no Redis required",
    )
    args = parser.parse_args(argv)

    if args.local:
        os.environ["PEARL_LOCAL_MODE"] = "1"

    import uvicorn

    uvicorn.run("pearl.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
