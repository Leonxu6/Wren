"""wren-metrics:监测库 CLI(W6)。跑在 bot 进程之外(cron),只读消费 data/。

  wren-metrics ingest                  # 增量幂等灌库(cron 每 ~15min)
  wren-metrics query [name]            # 列出/跑命名看板查询
  wren-metrics diagnose --chat-id X    # 某用户完整旅程(人工深挖)
  wren-metrics forget --chat-id X      # 硬删某用户监测行(对齐 /delete)
"""

from __future__ import annotations

import argparse
from typing import Any

from .db import connect
from .diagnose import diagnose
from .ingest import forget, ingest
from .queries import NAMED_QUERIES, run_named


def _print_table(cols: list[str], rows: list[tuple[Any, ...]]) -> None:
    print(" | ".join(cols))
    print("-" * 60)
    for r in rows:
        print(" | ".join("" if v is None else str(v) for v in r))
    print(f"({len(rows)} rows)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wren-metrics", description="Wren 监测库(只读消费 data/)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest", help="增量幂等灌库")
    p_q = sub.add_parser("query", help="跑命名看板查询(无参=列出)")
    p_q.add_argument("name", nargs="?", help="查询名;省略则列出全部")
    p_d = sub.add_parser("diagnose", help="某用户完整旅程")
    p_d.add_argument("--chat-id", required=True)
    p_f = sub.add_parser("forget", help="硬删某用户监测行")
    p_f.add_argument("--chat-id", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        print(f"ingested: {ingest()}")
    elif args.cmd == "diagnose":
        print(diagnose(args.chat_id))
    elif args.cmd == "forget":
        forget(args.chat_id)
        print(f"forgotten: {args.chat_id}")
    elif args.cmd == "query":
        if not args.name:
            for name, (desc, _) in NAMED_QUERIES.items():
                print(f"  {name:24s} {desc}")
            return
        con = connect(read_only=True)
        try:
            cols, rows = run_named(con, args.name)
            _print_table(cols, rows)
        finally:
            con.close()
