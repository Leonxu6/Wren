"""看板命名 SQL(W6;Datasette 把每条变成命名页)。映射产品目标(50-200 口味对齐日活、订阅,
非增长/DAU);**等级进展是头号指标**。per_user_overview 让「有问题的用户」一眼浮上来(D2.2)。

注:turns 列 turn_day/frozen(day、freeze 是 DuckDB 保留词);settlements 用 night/freeze_before/after。
"""

from __future__ import annotations

from typing import Any

import duckdb

# name -> (说明, SQL)
NAMED_QUERIES: dict[str, tuple[str, str]] = {
    "acquisition_by_source": (
        "按深链来源的新用户数(归因宣传渠道)",
        """
        SELECT COALESCE(source,'unknown') AS source, count(*) AS new_users,
               min(first_seen) AS first, max(first_seen) AS latest
        FROM users GROUP BY 1 ORDER BY new_users DESC
        """,
    ),
    "activation_by_source": (
        "激活率:/start 后是否发过真实消息(没发=bounce)",
        """
        SELECT COALESCE(source,'unknown') AS source, count(*) AS started,
               count(first_user_msg_ts) AS activated,
               round(100.0*count(first_user_msg_ts)/nullif(count(*),0),1) AS activation_pct
        FROM users GROUP BY 1 ORDER BY started DESC
        """,
    ),
    "retention_by_source": (
        "留存:首发当日 cohort 的 D1/D7 回访(按来源)",
        """
        WITH act AS (
            SELECT t.chat_hash, COALESCE(u.source,'unknown') AS source,
                   CAST(u.first_user_msg_ts AS DATE) AS cohort_day, t.turn_day AS active_day
            FROM turns t JOIN users u USING (chat_hash)
            WHERE t.is_user_turn AND u.first_user_msg_ts IS NOT NULL
            GROUP BY 1,2,3,4)
        SELECT source, count(DISTINCT chat_hash) AS cohort_n,
               count(DISTINCT chat_hash) FILTER (WHERE active_day = cohort_day + INTERVAL 1 DAY) AS d1,
               count(DISTINCT chat_hash) FILTER (WHERE active_day = cohort_day + INTERVAL 7 DAY) AS d7
        FROM act GROUP BY 1 ORDER BY cohort_n DESC
        """,
    ),
    "level_distribution": (
        "等级分布(头号指标):每用户当前 level = 最近一次结算的 lv_after,回退到最近一轮的 lv",
        """
        WITH latest_settle AS (
            SELECT chat_hash, lv_after AS lv,
                   row_number() OVER (PARTITION BY chat_hash ORDER BY ts DESC) rn FROM settlements),
        latest_turn AS (
            SELECT chat_hash, lv,
                   row_number() OVER (PARTITION BY chat_hash ORDER BY ts DESC) rn FROM turns),
        cur AS (
            SELECT u.chat_hash,
                   COALESCE((SELECT lv FROM latest_settle s WHERE s.chat_hash=u.chat_hash AND s.rn=1),
                            (SELECT lv FROM latest_turn t WHERE t.chat_hash=u.chat_hash AND t.rn=1), 0) AS lv
            FROM users u)
        SELECT lv, count(*) AS users FROM cur GROUP BY lv ORDER BY lv
        """,
    ),
    "level_transitions": (
        "每晚结算的升/降/新冻结/解冻(关系在动吗)",
        """
        SELECT night,
               count(*) FILTER (WHERE lv_delta > 0) AS promotions,
               count(*) FILTER (WHERE lv_delta < 0) AS regressions,
               count(*) FILTER (WHERE NOT freeze_before AND freeze_after) AS new_freezes,
               count(*) FILTER (WHERE freeze_before AND NOT freeze_after) AS thaws
        FROM settlements GROUP BY night ORDER BY night
        """,
    ),
    "time_to_level": (
        "中位达 Lv2 / Lv3 天数(从首条消息算)",
        """
        WITH reach AS (
            SELECT chat_hash,
                   min(night) FILTER (WHERE lv_after >= 2) AS lv2_night,
                   min(night) FILTER (WHERE lv_after >= 3) AS lv3_night
            FROM settlements GROUP BY chat_hash)
        SELECT median(date_diff('day', CAST(u.first_user_msg_ts AS DATE), r.lv2_night)) AS median_days_to_lv2,
               median(date_diff('day', CAST(u.first_user_msg_ts AS DATE), r.lv3_night)) AS median_days_to_lv3
        FROM reach r JOIN users u USING (chat_hash)
        """,
    ),
    "proactive_daily": (
        "主动消息:到判断的条数 vs 实发 vs 压制(P5;门级压制不落 trace,见盲点)",
        """
        SELECT turn_day AS day,
               count(*) AS proactive_judged,
               count(*) FILTER (WHERE replied) AS proactive_fired,
               count(*) FILTER (WHERE NOT replied) AS impulse_passed,
               round(100.0*count(*) FILTER (WHERE replied)/nullif(count(*),0),1) AS fire_pct
        FROM turns WHERE kind='proactive' GROUP BY turn_day ORDER BY turn_day
        """,
    ),
    "engagement_daily": (
        "每日参与:用户消息数 + 沉默率(reply=False 占 reactive 比)",
        """
        SELECT turn_day AS day,
               count(*) FILTER (WHERE kind='reactive' AND is_user_turn) AS user_msgs,
               round(100.0*count(*) FILTER (WHERE kind='reactive' AND NOT replied)
                     /nullif(count(*) FILTER (WHERE kind='reactive'),0),1) AS silence_pct
        FROM turns GROUP BY turn_day ORDER BY turn_day
        """,
    ),
    "cost_daily": (
        "成本:每日 turn 数 + completion token(按模型 flash/pro 分;⚠️只 completion,为下界)",
        """
        SELECT turn_day AS day, count(*) AS turns,
               sum(COALESCE(s1_tokens,0)+COALESCE(s2_tokens,0)) AS completion_tokens,
               sum(s1_tokens) FILTER (WHERE s1_model LIKE '%flash%') AS flash_s1_tokens
        FROM turns GROUP BY turn_day ORDER BY turn_day
        """,
    ),
    "latency_daily": (
        "每日延迟 p50/p95(ms)",
        """
        SELECT turn_day AS day,
               CAST(quantile_cont(s1_latency_ms, 0.5) AS INTEGER) AS s1_p50,
               CAST(quantile_cont(s1_latency_ms, 0.95) AS INTEGER) AS s1_p95,
               CAST(quantile_cont(s2_latency_ms, 0.5) AS INTEGER) AS s2_p50
        FROM turns GROUP BY turn_day ORDER BY turn_day
        """,
    ),
    "settlement_health": (
        "夜结算健康:每晚跑了几人、成功几人(parse_ok)、v4-pro token",
        """
        SELECT night, count(*) AS settlements_run,
               count(*) FILTER (WHERE parse_ok) AS settlements_ok,
               sum(settle_tokens) AS settle_tokens
        FROM settlements GROUP BY night ORDER BY night
        """,
    ),
    "per_user_overview": (
        "每用户下钻:有问题的用户置顶(冻结 / 沉默率高 / 卡级);D2.2 一眼可见",
        """
        SELECT u.chat_hash, COALESCE(u.source,'unknown') AS source,
               count(t.turn_id) FILTER (WHERE t.is_user_turn) AS user_msgs,
               max(t.lv) AS lv,
               bool_or(t.frozen) AS ever_froze,
               round(100.0*count(t.turn_id) FILTER (WHERE t.kind='reactive' AND NOT t.replied)
                     /nullif(count(t.turn_id) FILTER (WHERE t.kind='reactive'),0),1) AS silence_pct,
               count(t.turn_id) FILTER (WHERE t.kind='proactive') AS proactive_n,
               max(t.turn_day) AS last_active_day
        FROM users u LEFT JOIN turns t USING (chat_hash)
        GROUP BY u.chat_hash, u.source
        ORDER BY ever_froze DESC, silence_pct DESC NULLS LAST
        """,
    ),
}


def run_named(con: duckdb.DuckDBPyConnection, name: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    """跑一条命名查询,返回(列名, 行)。"""
    _, sql = NAMED_QUERIES[name]
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, cur.fetchall()
