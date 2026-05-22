# ADR 0001 — MVP 生产级分发:部署 / 监测 / 付费 seam

状态:已接受(2026-05-22,与 Leon 经 /grill-me 两轮 + 验收先行对齐)。
背景:产品(Wren)到 MVP,要对外分发。目标极小且故意小(PRD §1.3:50–200 口味对齐日活、订阅,非增长)。

## 决策
1. **验收先行**。先与 Leon 定 4 维可度量门(D1 隔离/完整性、D2 可观测/闭环、D3 部署/可靠性、
   D4 可维护/付费 seam),再实现,迭代到全绿才算完。门写在 `tasks/` 计划与本仓库测试里。
2. **发布物 = `origin/main` 全量 P0–P6**(先快进本地 main)。P5 主动消息缺的 live 触发器在本轮补上。
3. **完全公开链接**(免费收信号)。连带硬需求:调试命令(`/setlevel`/`/tick`)owner 鉴权、每用户限流、
   全局每日成本天花板 —— 否则任何人 `/setlevel 6` 绕过「关系是挣来的」(PRD §3.3)+ 花费无上限。
4. **主动消息 live scheduler 现在就建**(`scheduler.proactive_tick`,run_repeating ~10min)。机械新近度
   护栏让路(§0:计时非分类器,不在对话中插嘴)。天然被等级门控(Lv0-1=0)。
5. **部署 = 便宜 VPS + Docker**,单实例(long-poll + 内存锁不可水平扩容),restart=always,持久卷,
   备份**可恢复演练**通过才放行。时区由夜结算自带(ET，TZ-aware)。
6. **存储维持 per-user markdown 作真相源**(human-readable trace 是 Leon 调声音的方式,§0),不迁 DB;
   完整性靠原子写(temp→rename)+ 跨用户隔离测试 + 共享 world 单飞锁。
7. **监测 = 同机自托管 DuckDB**(`src/wren/ops/`,只读消费 data/,绝不被 core/bot import)。
   **内容不出机器**:库只存指标+维度,chat_id 哈希;原始 transcript 留机器上供 `diagnose` 人工深挖。
   自纠闭环是「完整捕获 + 显眼看板 + 按需人工深挖」,非常驻自动判定管线。
8. **付费 = 预切 seam,本期不建**。per-user `tier`(gate-key 非积分,缺省 premium = v1 全员免费);
   日后加订阅 = 支付 webhook → `write_tier`,free 在 `core/proactive` 已短路成 0,**零改 core**。

## 已知取舍 / 盲点(诚实记录)
- 18+ 仅文案、无强制(Telegram 无真实年龄门;靠通知 + 内容天花板 suggestive-never-explicit 兜底)。
- 单实例是已知天花板(50–200 用户足够)。
- 成本估算为下界(trace 只记 completion token);错误率 / 主动门级压制原因未落 trace —— 留 seam,
  看板对应格子标 "n/a"。
- P7(Lv4 深度脆弱)仅部分实现,本轮不在范围。
