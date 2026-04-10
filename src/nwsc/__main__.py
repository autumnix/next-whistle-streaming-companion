"""Entry point: python -m nwsc"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Next Whistle Streaming Companion")
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to config YAML file (default: NWSC_CONFIG env var or config.yaml)",
    )
    parser.add_argument(
        "--host", default=None, help="Override server host",
    )
    parser.add_argument(
        "--port", type=int, default=None, help="Override server port",
    )
    args = parser.parse_args()

    if args.config:
        os.environ["NWSC_CONFIG"] = args.config

    from nwsc.config import load_config
    config = load_config(args.config)

    host = args.host or config.server.host
    port = args.port or config.server.port

    uvicorn.run(
        "nwsc.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
        log_level=config.server.log_level,
    )


if __name__ == "__main__":
    main()
