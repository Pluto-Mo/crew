---
name: starixs
description: "The user's own division-of-labour rules for heavy work: brain, hand, review, verify. A hook puts the standing rule in front of you on each task message; this skill holds the fuller rules and the per-host split. Use it when work is multi-step, touches several files or modules, or ends in something hard to undo (deploy, publish, delete, send, pay); run it before starting, and again when a task that looked light turns out heavy. Not needed for chat, one-line answers, translation, naming, or a single small edit."
---

# starixs

Division of labour for heavy work. The point is not to add models for their own
sake: it is to stop one context from being author, reviewer and judge at once,
and to keep the expensive checks for where a mistake would actually cost
something.

## How this works, in three layers

| Layer | Runs when | What it does |
|---|---|---|
| **Gate** (`scripts/gate.py`) | Every user message, via a host hook | Puts the standing rule in front of you in full. Adds the undo rules when the message mentions an irreversible action. Records one line per message — time, host, session, which rules, length, directory; never the content. |
| **This skill** | Read once, holds for the session | The four roles, the brakes, the reviewer table. |
| **Split** (`scripts/starixs.py`) | Heavy work only (`steps=multi`) | Works out the brain/hand/review/verify split for this host, or replays the one the user confirmed. |

The gate does only what can be decided from the literal text: is this the first
message, is it a short follow-up, does it mention something irreversible.
Whether a message is a correction, or whether the task is heavy, is left to you
— you can read intent, the gate cannot.

## 分工

重活拆成四个角色，**只用这次活需要的那几个**。

| 角色 | 做什么 | 不许做什么 |
|---|---|---|
| **Brain（脑）** | 定方案和硬判断 | 几步就能做完的活也去问 |
| **Hand（手）** | 干活 | 自己审自己 |
| **Review（审查）** | 在全新只读上下文里按目标检查结果 | 做过这活；比干活的模型弱 |
| **Verify（验证）** | 跑真能失败的东西：测试、真实路径 | 用模型意见代替 |

## 调用

```bash
python3 scripts/starixs.py --tags type=engineering,shape=whole,risk=reversible,for=self,steps=multi
```

- `steps=one`（一口气的活）、闲聊、翻译、起名 → 什么都不出
- `steps=multi` → 首次给完整分工说明（含"只读探查本宿主有什么"）
- 同一对话再次调用 → 只给安静版（不再探查）
- `--from 派单` → 子代理/帮手，不给分工（不往下嵌套）
- 直接运行不带 `--tags` → 按重活处理，如用户点名「starixs 分工」

开关与固定分工：

```bash
python3 scripts/starixs.py --off                      # 「分工关」：不再给分工说明，规则照常
python3 scripts/starixs.py --on                       # 「分工开」
python3 scripts/starixs.py --set "brain=X;executor=Y;review=Z;helpers=W"
python3 scripts/starixs.py --set none                 # 这家宿主不要建议，之后不再提
```

`--set` 只在用户明确同意后调用。**认不出的宿主不能存分工**——防止在 Codex 里定的
配置被误用到别家。

## 门（gate）

```bash
python3 scripts/gate_install.py            # dry run: 看会写什么
python3 scripts/gate_install.py --apply    # 装
python3 scripts/gate.py --check            # 钩子装了没有、规则读得到不
python3 scripts/gate_install.py --uninstall
```

装的东西：

- 数据目录里一份**明文独立版** `gate.py` + `gate_rules.json`（规则原文原样抄进去）
- Claude Code：`~/.claude/settings.json` 两条钩子（每条消息、压缩之后），原文件先备份
- Codex：本地插件市场里的 `starixs-gate` 插件，用户得在 `/hooks` 里信任一次

**门的退出码永远是 0**：它出任何错都不能拦住用户发消息。**它不判断语义**，只按字面
放不放规则。**它不记消息内容**，只记长度和放了哪几条。

## 三条硬规则（脚本每次都会带上）

**一、小任务要严格判。** 干完之后按实际改动判，不是按开头的观感。全部满足才算小：
验证跑了、通过、覆盖本次改动、且没有改测试让它通过；diff ≤ 2 个文件、≤30 行；
不碰公开接口、存储数据或迁移、权限、安全、支付、发布配置、并发；没有报错、
没有东西阻断验证、改动没超出要求；可撤销、只有用户自己用、用户没要求 review。
**跑不了验证的活一律不算小。**

**二、review 最多三轮。** 三轮后还有新问题 → 报告未决项，不许继续，不许自行加固。

**三、按代价定 reviewer，不按最低可用定。**

| 活 | reviewer |
|---|---|
| 小到你可以自己对目标检查 | 你自己 |
| ≤200 行、可跑、可撤销 | 同模型、中等档位、全新只读上下文 |
| 超过 200 行 / 跨模块 / 碰敏感区 | 强一档模型、接近其顶档 |
| 难撤销 / 别人照它办事 / 跑不了 | 能用最强模型、接近顶档 |

太弱的 reviewer 只会报"没问题"，你永远收不到信号。不许超过该行规定的上限。
用户确认过 reviewer 就用用户那个。

## 升档

只在有信号时升：验证连续失败两次，或 review 连续两次返回同类问题。
**先升档位 → 再换模型 → 最后加帮手。**

## 上下文要瘦

后面每一步都会重读全部上下文。只读需要的部分（行区间、搜索），不整段读文件、
日志、数据、页面、截图。需要的是结论而不是原文时，交给最便宜能做的帮手读，
带回结论和依据的确切原行。编辑和判断留在主上下文。

## 交付时

交用户要的东西，然后几行说明：跑了什么验证、结果如何，review 查到什么、
哪一项还没决，是否值得更深一轮 review。

**不汇报分工**（谁干的、问了几次脑、review 进行得怎样）——除非用户问。
没验成的，用几个字说明；发现了未决问题，点名。

## 记账

只存本机，不上传，记录里没有型号：

```
~/.local/share/starixs/          （STARIXS_HOME 可改）
├── config.json               model_split: true/false
├── model_roles.json          {宿主: {brain, executor, review, helpers}} 或 {宿主: {declined: true}}
└── uses.jsonl                每次调用的 host / shape / roles_set / division / brake
```

不同用户的凭据不能借用；不同宿主的配置不能串用。

## 宿主没有子代理机制时

规则照旧：全新上下文 = 新会话；review = 拿自己的 diff 对目标读，而不是重读自己的
计划。哪一步做不到，说出来。
