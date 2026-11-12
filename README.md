# @starixs/crew

Division of labour for heavy work, as an agent skill. Four roles — **brain, hand,
review, verify** — plus the machinery to make "done" mean something.

The package is `@starixs/crew`: starixs is the company, crew is the thing you
hire — four jobs on one boat. The command it installs is `starixs`.

Built for teams: one person maintains it, everyone installs it, nobody has to
trust a sealed binary.

---

## Architecture: three layers

| Layer | Runs when | Job |
|---|---|---|
| **Gate** `scripts/gate.py` | Every user message, via a host hook | Puts the standing rule in front of the agent in full; adds two undo rules when the message mentions an irreversible action; records one line per message (time, host, session, which rules, length, directory — never content) |
| **Skill** `SKILL.md` | Read once per session | The four roles, the brakes, the reviewer table |
| **Split** `scripts/starixs.py` | Heavy work only | Resolves the brain/hand/review/verify split for this host, or replays the user's confirmed one |

Why a gate at all: without it the rules only appear when the agent decides to go
look them up — and an agent is least likely to look things up precisely when it
is rushing. Why the gate stays dumb: it only decides what is visible in the
literal text (first message? short follow-up? mentions something irreversible?).
"Is this a correction, is this heavy" needs intent, so that stays with the agent.

Three properties the gate holds no matter what:

- **Exit code is always 0.** A gate that can block a user's message is worse than no gate.
- **It never records message content.** Length and rule names only.
- **It reads only the user's own words.** Pasted material (`<pasted_content>`, code blocks, quoted lines) and host notifications do not trigger the undo rules.

## What it does

When work is heavy (multi-step, several modules, or ending in something hard to
undo), the agent runs `plan`. It gets back:

- the four roles and what each must not do
- an instruction to discover, read-only, what *this* host can actually run
- the brake rules: what counts as small, when to consult the brain, how many review rounds
- a reviewer table keyed to what a miss would cost

**No model names, no effort-level names, no host capability list** is written
anywhere in this package. The agent discovers what exists at run time and
decides. A model refresh never needs a code change. This is the single most
important design constraint, and a test enforces it.

## Why four roles

One context being author, reviewer and judge at once is how "done" becomes a
claim instead of a fact. Splitting the roles is cheap; conflating them is
expensive in exactly the way you notice too late.

| Role | Does | Must not |
|---|---|---|
| Brain | Decides the approach and hard calls | Be consulted for a handful of steps |
| Hand | Does the work | Judge its own result |
| Review | Reads the result against the goal, fresh read-only context | Have done the work; be weaker than the hand |
| Verify | Runs something that can fail | Be replaced by a model's opinion |

## Install

### Route A — one command, nothing to trust

```bash
npx -y skills add Pluto-Mo/crew --skill crew -g -y
```

That copies the whole skill folder into `~/.agents/skills/crew/` — SKILL.md, the
four scripts, the rule texts. It runs with no network afterwards. This is the
route to use when you just want the split.

### Route B — the same thing plus the per-message gate

```bash
npx -y github:Pluto-Mo/crew install --apply --with-gate
npx -y github:Pluto-Mo/crew check
```

Route A gives you the rules on demand. Route B also puts them in front of the
agent on **every** task message, including the ones where it is rushing and would
not think to look anything up. That needs a hook, and a hook needs a stable file
on disk, so the installer copies a plain-text `gate.py` and the rule texts into
`~/.local/share/starixs/` and wires the host.

`install` without `--apply` prints every path it would write and changes nothing.

There is no postinstall hook. Nothing touches your agent config until you run
`install --apply`. A package that silently rewires your agent on install is
exactly what the gate's own audit rules would flag.

## Why the repo looks like this

```
crew/
├── skills/crew/          <- `skills add` copies this folder, and only this one
│   ├── SKILL.md
│   ├── scripts/          <- mirrored from ../scripts
│   ├── references/rules/ <- mirrored from ../references/rules
│   └── config.json
├── scripts/              <- single source of truth; the npm entry point and tests use these
├── references/rules/     <- ditto
├── bin/starixs.js        <- npm entry point
├── sync.py               <- copies root -> skills/crew, and --check fails on drift
└── tests/
```

Two copies of the same script is a trap: edit one, forget the other, ship a
stale skill. `sync.py` is the only supported way to update the skill folder, and
both `npm test` and `npm run prepack` fail when the two disagree. Nothing can be
published with a drifting skill.

## Updates reach the installed gate

A colleague's skill folder updates on their next install, but the **plain-text
copy of `gate.py` in their state directory** would otherwise stay at the old
version — and new rules would never reach it. That is a silent failure, the
worst kind.

So every run of `scripts/starixs.py` first calls `gate_install.refresh_installed()`:

- if no gate is installed, nothing happens (it does not install one)
- if the installed gate is older, `gate.py` and `gate_rules.json` are replaced
- if the installed gate is **newer**, it is left alone — an old copy cannot downgrade a new gate
- host hooks and settings are **never** touched by an update; those are the user's files

## The policy numbers

`config.json` holds one switch, `model_split`. Everything else — what counts as
small, how many review rounds, which reviewer for which size — lives in the rule
text, the way the design intends. There is no knob to turn that would quietly
change the standard a team is held to.

## Design decisions worth arguing about

**The gate decides only what the literal text shows.** First message, short
follow-up, mentions something irreversible. Whether a message is a correction,
or whether a task is heavy, needs intent — so that stays with the agent. A gate
that guesses intent wrong is worse than one that stays silent.

**The gate's exit code is always 0.** If it can block a user's message, it is a
liability, not a safeguard. Every failure mode in it ends in "print nothing,
exit 0".

**The gate does not record message content.** One line per message: time, host,
session id, which rules were placed, message length, working directory. Enough
to audit, nothing to leak.

**Records carry no model names.** A test fails the build if a model slug or
effort name appears in the source, the SKILL.md, or the rule files. Model choice
is a run-time judgement, not a shipped constant.

**Splits are per host.** A split pinned in Codex is never applied to Claude Code.
An unrecognised host cannot save one at all.

**The gate hook is wired by an installer that backs up first.** `settings.json`
is someone else's file. It gets copied to `.bak` before any edit, and the
uninstaller removes only the hook entries that carry our marker.

**The hook command uses a stable interpreter.** Not the interpreter that happened
to run the installer — that is often a temporary venv that disappears, leaving a
hook that fails silently forever.

## Layout

```
starixs/
├── SKILL.md              the skill text the agent reads
├── config.json           policy numbers
├── install.py            dry-run-first installer
├── scripts/starixs.py       the whole implementation, stdlib only
└── tests/test_starixs.py    39 checks, no external deps, no network
```

## Requirements

Python 3.9+. Standard library only. No network calls, no credential reads.

## Verifying it yourself before distribution

```bash
python3 tests/test_starixs.py      # expect: 39 passed, 0 failed
python3 install.py              # dry run, read every line it prints
python3 scripts/starixs.py doctor  # environment check, declares "network": "unused"
```

Grep it. It is 700 lines of plain Python with no obfuscation, no dynamic imports,
no network calls and no credential reads. That is the point of shipping it this
way rather than as a sealed package.
