"""eval —— Phase 0 打分内核(机械门 + LLM judge)+ harness/bakeoff + trace 回放。

红线(§0①):本包是 **eval 专用,绝不进生产回复链路**(src/wren/core/* 不得 import 本包)。
它是机械/语义检查器,不是踩雷检测器/情感打分器/积分系统。
"""
