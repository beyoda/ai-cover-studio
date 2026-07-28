"""python -m aivoice_studio.notifier — outbox consumer (mock by default)."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from aivoice_studio.notifier.config import resolve_feishu_mode
from aivoice_studio.notifier.feishu_client import (
    FeishuAuthError,
    FeishuClientError,
    MockFeishuClient,
    build_feishu_client,
)
from aivoice_studio.notifier.outbox_consumer import OutboxConsumer


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AIVOICE outbox notifier")
    p.add_argument("--jobs-root", default=None, help="Override jobs/ directory")
    p.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Scan and consume once then exit (default)",
    )
    p.add_argument(
        "--real",
        action="store_true",
        help="Use RealFeishuClient (requires FEISHU_APP_ID/SECRET); default mock",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    mode = resolve_feishu_mode(real_flag=bool(args.real))
    try:
        client = build_feishu_client(mode=mode)
    except FeishuAuthError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "mode": mode}, ensure_ascii=False))
        print(f"error={exc}", file=sys.stderr, flush=True)
        return 2
    except FeishuClientError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "mode": mode}, ensure_ascii=False))
        return 2

    consumer = OutboxConsumer(args.jobs_root, client=client)
    stats = consumer.run_once()
    report = stats.to_dict()
    report["mode"] = mode
    if isinstance(client, MockFeishuClient):
        report["mock"] = client.as_dict()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        f"mode={mode} "
        f"consumed_count={stats.consumed_count} "
        f"sent_count={stats.sent_count} "
        f"skipped_count={stats.skipped_count} "
        f"failed_count={stats.failed_count}",
        flush=True,
    )
    return 0 if stats.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
