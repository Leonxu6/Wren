# 开发工作流 (DEV_WORKFLOW)

> 配套 `tasks/todo.md`(开发计划)。本文 = 这个仓库怎么协作开发的约定。
> 语言:正文中文;Wren 的对白 / voice 样本英文(沿用 PRD §7)。

---

## 分支与 worktree 模型:**按 issue 开 worktree**

- `HERR/` 主仓库**常驻 `main`**,保持干净——**不在 main 上直接写代码**。
- **每个 issue = 一个 worktree + 一个同名分支**,放在 sibling 目录 `../HERR-worktrees/<issue-id>/`。
  - `issue-id` 命名:`p<phase>-<slug>`,例 `p0-mech-gate`、`p0-bakeoff`、`p1-telegram-slice`。
  - 与 `tasks/todo.md` 里的 issue **一一对应**;互不依赖的 issue 可**并行**(可挂不同 agent)。

### 常用命令

```bash
# 开一个 issue 的 worktree(在主仓库 HERR/ 里跑)
git worktree add ../HERR-worktrees/p0-mech-gate -b p0-mech-gate

# 列出所有 worktree
git worktree list

# issue 做完、已合回 main 后清理
git worktree remove ../HERR-worktrees/p0-mech-gate
git branch -d p0-mech-gate

# 合并(在主仓库 main 上;被 merge 的分支可仍 checkout 在其 worktree)
git merge --no-ff p0-mech-gate
```

### 与 Claude Code agent 配合

- **临时探索 / 并行分析**:`Agent(..., isolation: "worktree")` 会自建临时 worktree(无改动自动清理)。
- **正式 issue**:用上面手工 `git worktree add` 的**持久 worktree**(命名对得上 `tasks/todo.md`),便于多轮迭代和 review。
- 一个 issue 收尾时在它的 worktree 里跑 **`/go`**:验证(journey / conformance / eval)→ 修到过 → 简化 → 开 PR / 合并。

---

## commit 规范

- 信息祈使句、聚焦一件事;每个 commit 末尾加:

  ```
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- **只在被要求时 push**;outward / 不可逆动作先确认。

---

## 红线(写任何代码 / prompt / copy 前自检)

- 不违反 **PRD §3 六条产品魂**(她不为你存在 / 能拒绝你 / 关系靠 earn / 她有自己观点……)。
- 不违反 **ARCHITECTURE §0 两铁律**:
  1. **涌现 > 模块**——不做独立的踩雷检测器 / 情感打分器 / **积分制关系系统**(它们活在 LLM call 里涌现)。
  2. **轻量优先,留好 seam**——在模型路由 / 记忆召回 / eval 处预留升级缝。
- **冲突解决序**:§3 红线 > `ARCHITECTURE.md` 决策 > PRD 正文(PRD §15 仍是开放提案,非定案)。

---

## 起步

- 建造顺序见 `tasks/todo.md`(**风险优先**;**Phase 0 在任何产品代码之前**)。
- **Phase 0 = voice bake-off**,掐 §15#4 头号风险(便宜模型 DeepSeek 能否撑住 Wren 的干式英文 texting voice)——这一步不过,后面全免谈。
