"""ops:监测/诊断层(W6)。data/ 的【只读消费者】,绝不被 core/ 或 bot/ import(同 eval/ 边界)。

- ingest:trace.jsonl + settlement.jsonl + source.md → DuckDB(只存指标+维度,绝不存原文;chat_id 哈希)。
- queries:看板命名 SQL(获取/留存/等级进展/freeze/主动/沉默/成本)。
- diagnose:某用户完整旅程的人类可读 dump(读机器上的原始 trace,供出问题时人工深挖)。
"""
