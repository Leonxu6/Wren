"""原子文件写(W4 数据完整性):同目录临时文件 + os.replace(POSIX 原子 rename)。

崩在写入中途 → 正本不动、无半截文件(靠 temp+rename 的原子性,不靠 fsync);fsync 加掉电持久性。
用于所有「整篇覆盖」的状态文件。JSONL 追加(trace)走单次整行 write + 读侧跳坏行(见 trace.py),
不在此列。
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """整篇原子写:写同目录 .tmp → fsync → os.replace。失败则清临时文件、正本不动。

    os.replace 是原子 rename:并发/崩溃下读者要么见旧内容、要么见新内容,绝不见写到一半的半截。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
