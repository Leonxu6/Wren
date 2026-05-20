"""生产链路(per-turn flow)。think→speak 两次 LLM call,judgment 锁在 Step1。

红线(§0①):本包**不得 import wren.eval**(eval 是观测/打分,不进生产决策链路)。
"""
