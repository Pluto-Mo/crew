---
name: starixs-full
description: "The full reference text for crew. Not installed as a skill — read it when you want the whole design in one file. The installed skill is skills/crew/SKILL.md."
---

# crew — full reference

Division of labour for heavy work. The point is not to add models for their own
sake: it is to stop one context from being author, reviewer and judge at once,
and to keep the expensive checks for where a mistake would actually cost
something.

---

## 1. Three layers

| Layer | Runs when | What it does |
|---|---|---|
| **Gate** (`scripts/gate.py`) | Every user message, via a host hook | Puts the standing rule in front of the agent in full. Adds the undo rules when the message mentions an irreversible action. Records one line per message — time, host, session, which rules, length, directory; never the content. |
| **Skill** (`skills/crew/SKILL.md`) | Read once, holds for the session | The four roles, the brakes, the reviewer table, how to set up and how to remove. |
| **Split** (`scripts/starixs.py`) | Heavy work only (`steps=multi`) | Works out the brain/hand/review/verify split for this host, or replays the one the user confirmed. |

The gate does only what can be decided from the literal text: is this the first
message, is it a short follow-up, does it mention something irreversible.
Whether a message is a correction, or whether the task is heavy, is left to the
agent — it can read intent, the gate cannot.

### 三层

| 层 | 什么时候跑 | 干什么 |
|---|---|---|
| **门** | 每条用户消息，由宿主钩子调用 | 把常驻规则原文整段放到 AI 眼前；消息里出现收不回的动作时加放两条；每条消息记一行（时间、宿主、会话、放了哪几条、长度、目录），不记内容 |
| **技能** | 读一次，整场对话有效 | 四个角色、刹车、reviewer 分级表、怎么装、怎么删 |
| **分工** | 只有重活（`steps=multi`） | 按这台宿主的实际情况定脑/手/审查/验证的分工，或重放用户确认过的那一套 |

门只做字面能判的事：是不是第一条消息、是不是短回话、有没有提到收不回的动作。
是不是纠正、是不是重活，要靠读懂意图，留给 AI——门读不懂。

---

## 2. Four jobs

| Job | Does | Must not |
|---|---|---|
| **Brain** | Decides the approach and the hard calls | Be consulted for a handful of steps |
| **Hand** | Does the work | Judge its own result |
| **Review** | Reads the result against the goal, in a fresh read-only context | Have done the work; be a weaker model than the hand |
| **Verify** | Runs something that can fail — tests, the real path | Be replaced by a model's opinion |

### 四个岗位

| 岗位 | 做什么 | 不许做什么 |
|---|---|---|
| **脑** | 定方案和硬判断 | 几步就能做完的活也去问 |
| **手** | 干活 | 自己审自己 |
| **审查** | 在全新只读上下文里按目标检查结果 | 做过这活；比干活的模型弱 |
| **验证** | 跑真能失败的东西：测试、真实路径 | 用模型意见代替 |

---

## 3. Calling the split

```bash
python3 scripts/starixs.py --tags type=engineering,shape=whole,risk=reversible,for=self,steps=multi
```

- `steps=one` (a single pass), chat, translation, naming → nothing is printed
- `steps=multi` → first call gives the full block, including the read-only probe of what this host offers
- same conversation, later call → quiet block, no probing
- `--from 派单` → a helper: no split, it does its piece and stops
- run with no `--tags` → treated as heavy work, for when the user asks for the split by name

```bash
python3 scripts/starixs.py --off                      # stop the note; the rules still apply
python3 scripts/starixs.py --on
python3 scripts/starixs.py --set "brain=X;executor=Y;review=Z;helpers=W"
python3 scripts/starixs.py --set none                 # this host: no suggestion, ever
```

`--set` only after the user agrees. A split pinned for one host is never applied
to another: an unrecognised host cannot save one at all.

### 调用

- `steps=one`（一口气的活）、闲聊、翻译、起名 → 什么都不出
- `steps=multi` → 首次给完整分工说明，含"只读探查本宿主有什么"
- 同一对话再次调用 → 只给安静版，不再探查
- `--from 派单` → 子代理/帮手，不给分工，不往下嵌套
- 不带 `--tags` 直接跑 → 按重活处理，用于用户点名要分工

`--set` 只在用户明确同意后调用。**认不出的宿主不能存分工**——防止在 Codex 里定的
配置被误用到别家。

---

## 4. Brakes

### 4.1 What counts as small

Judged after the work, from the actual change, never from how it looked at the
start. All of these must hold:

- verification ran, passed, covers this change, and no test was changed to make it pass
- the diff is at most 2 files and 30 lines added plus removed
- it touches no public interface, stored data or migration, permissions, security, payment, release configuration or concurrency
- nothing failed, nothing blocked verification, and the change stayed inside what was asked
- it is reversible, only the user is affected, and no review was asked for

**Work that cannot be run is never small.** A one-line change outside what was
asked for is still outside.

### 4.1 小任务的严格定义

干完之后按实际改动判，不是按开头的观感。全部满足才算小：

- 验证跑了、通过、覆盖本次改动，且没有改测试让它通过
- diff ≤ 2 个文件、≤30 行（增删合计）
- 不碰公开接口、存储数据或迁移、权限、安全、支付、发布配置、并发
- 没有报错、没有东西阻断验证、改动没超出要求
- 可撤销、只有用户自己受影响、用户没要求 review

**跑不了验证的活一律不算小。** 我没要的改动，哪怕一行，也在范围之外。

### 4.2 Review rounds

Three, then stop. If a review still finds new problems after three rounds,
report what is open instead of continuing. No self-imposed extra rounds, no
self-imposed hardening.

### 4.2 审查轮次

三轮，之后停。三轮后还有新问题 → 报告未决项，不许继续，不许自行加固。

### 4.3 Reviewer, by what a miss would cost

| The work | The reviewer |
|---|---|
| Small enough to check yourself against the goal | You |
| At most 200 lines, runnable, reversible | Same model as the hand, middle effort, fresh read-only context |
| Over that, across modules, or touching a public interface, stored data, permissions, security, payment, release config or concurrency | Next stronger model, high effort |
| Hard to undo, others act on it, or nothing can be run | Strongest available, top effort |

A reviewer weaker than the hand does not review — it can look things up for the
reviewer. A reviewer that is too weak reports nothing wrong, so no signal ever
comes. Do not go above the row the work falls in. If the user pinned a reviewer,
use that one.

### 4.3 按代价定 reviewer，不按最低可用定

| 活 | reviewer |
|---|---|
| 小到你可以自己对目标检查 | 你自己 |
| ≤200 行、可跑、可撤销 | 同模型、中等档位、全新只读上下文 |
| 超过 200 行 / 跨模块 / 碰敏感区 | 强一档模型、接近其顶档 |
| 难撤销 / 别人照它办事 / 跑不了 | 能用最强模型、接近顶档 |

太弱的 reviewer 只会报"没问题"，你永远收不到信号。不许超过该行规定的上限。
用户确认过 reviewer 就用用户那个。

---

## 5. Escalation

Go up only on a signal: verification failed twice, or a review returned the same
class of problem twice. **Raise the effort level before changing the model, and
change the model before adding a helper.**

### 升档

只在有信号时升：验证连续失败两次，或 review 连续两次返回同类问题。
**先升档位 → 再换模型 → 最后加帮手。**

---

## 6. Keep the context lean

Every later step re-reads all of it. Read the part you need — a line range, a
search — not whole files, logs, data dumps, page dumps or screenshots. When you
need the conclusion of something long, hand the reading to the cheapest helper
that can do it and take back the conclusion with the exact lines it rests on.
Keep edits and judgment calls with the main context.

### 上下文要瘦

后面每一步都会重读全部上下文。只读需要的部分（行区间、搜索），不整段读文件、
日志、数据、页面、截图。需要的是结论而不是原文时，交给最便宜能做的帮手读，
带回结论和依据的确切原行。编辑和判断留在主上下文。

---

## 7. On delivery

Say what verification ran and what it showed, what the review found and which
item is still open, whether a deeper review seems worth it. **Leave out how the
work was divided** — who did what, how often the brain was consulted, how the
review went — unless the user asks. If nothing could be verified, say so in a few
words; if a review found something still open, name it.

### 交付时

交用户要的东西，然后几行说明：跑了什么验证、结果如何，review 查到什么、
哪一项还没决，是否值得更深一轮 review。

**不汇报分工**（谁干的、问了几次脑、review 进行得怎样）——除非用户问。
没验成的，用几个字说明；发现了未决问题，点名。

---

## 8. State

Everything lives on this machine and is never uploaded. Records carry no model
names.

```
~/.local/share/starixs/          (STARIXS_HOME overrides)
├── config.json               model_split: true/false
├── model_roles.json          {host: {brain, executor, review, helpers}} or {host: {declined: true}}
├── uses.jsonl                per call: host / shape / roles_set / division / brake
├── gate.jsonl                per message: time / host / session / kind / rules / length / cwd
└── gate_state.json           last time each conversation passed the gate
```

Different users' credentials are never borrowed; different hosts' splits never
cross over.

### 记账

只存本机，不上传，记录里没有型号。不同用户的凭据不能借用；不同宿主的配置不能串用。

---

## 9. When the host has no subagents

The rules still apply: a fresh context means a new session, and review means
reading your own diff against the goal rather than re-reading your own plan. Say
which part you could not do.

### 宿主没有子代理机制时

规则照旧：全新上下文 = 新会话；review = 拿自己的 diff 对目标读，而不是重读自己的
计划。哪一步做不到，说出来。

---

## 10. Install and remove

```bash
npx -y skills add Pluto-Mo/crew --skill crew -g -y          # the skill
python3 ~/.agents/skills/crew/scripts/gate_install.py --apply    # the gate
python3 ~/.agents/skills/crew/scripts/gate_install.py --check    # is it live?
python3 ~/.agents/skills/crew/scripts/gate_install.py --uninstall --all   # remove everything
```

### 安装与卸载

一条命令装技能，一条装门，一条查状态，一条全删。
