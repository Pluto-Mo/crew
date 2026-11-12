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

## Give it to a colleague

Send them this:

> Use the crew skill to split heavy work and keep using it. If the skill is
> missing, install it first: `npx -y skills add Pluto-Mo/crew --skill crew -g -y`

That is the whole message. The skill text tells the agent to finish the setup
itself on first read — the hook, the rule texts, and a check that says whether
it is actually live. Nothing else to install, no clone, no npm login.

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

## Update

Just ask. Say 更新 / 升级 / update crew and the agent runs it — the trigger words
are in the skill's description, so it knows what that means:

```bash
npx -y skills add Pluto-Mo/crew --skill crew -g -y
python3 ~/.agents/skills/crew/scripts/gate_install.py --apply
python3 ~/.agents/skills/crew/scripts/starixs.py --version
```

The third line is the point: it prints the version you now have, so "updated" is
something you can read rather than something the agent asserts. Same for removal —
say 卸载 / 删除 and it runs `--uninstall --all`.

It overwrites the skill folder in place. Local edits to those files are lost —
by design: they are shipped files, not your config. Your settings live in
`~/.local/share/starixs` and an update never touches that directory.

### The gate follows on its own

The installed hook runs from `~/.local/share/starixs/gate.py`, a separate copy,
so replacing the skill folder does not by itself change what the hook injects.
Two mechanisms close that gap:

1. **Every run of `scripts/starixs.py` calls `refresh_installed()` first.** That
   replaces an older `gate.py` and `gate_rules.json`. This is the normal path: the
   agent runs the split on the first heavy task after an update, and the gate is
   current from then on. Nothing to remember.
2. **`--check` names the mismatch** when the installed copy is older than the
   skill's, so a stale gate is visible rather than silent.

An older skill can never downgrade a newer gate: the standalone copy carries a
version stamp, and `refresh_installed` refuses to go backwards.

Want the gate current right now instead of on next use:

```bash
python3 ~/.agents/skills/crew/scripts/gate_install.py --apply
```

### What an update never does

- It does not touch your host hook wiring. `settings.json` and the Codex plugin
  stay as they are; if the wiring itself needs changing, `--check` says so.
- It does not remove anything you turned on or off. `--off` stays off.
- It does not delete records. Those are yours.

## Uninstall

One command, from the installed copy:

```bash
python3 ~/.agents/skills/crew/scripts/gate_install.py --uninstall --all
```

That removes three things and nothing else:

| Removed | Where |
|---|---|
| the skill folder | `~/.agents/skills/crew` (or `~/.claude/skills/crew`) |
| the gate and rule texts | `~/.local/share/starixs` |
| the hook entries | `~/.claude/settings.json` (backup taken first), or the Codex plugin |

Three levels, because wanting one of them gone is not the same as wanting all
of it gone:

| Command | Removes |
|---|---|
| `--uninstall` | the hook entries and `gate.py`; keeps the record directory |
| `--uninstall --purge` | the above, plus `~/.local/share/starixs` |
| `--uninstall --all` | all of the above, plus the skill folder |

The record directory holds which rules were placed and the on/off switch. Those
are your files; deleting them should be a decision, not a side effect of removing
a hook — that is why it takes an extra flag.

If the skill folder is already gone, the hook can still be removed from a
checkout: `python3 scripts/gate_install.py --uninstall`.

Nothing outside those paths is touched. Every write to `settings.json` leaves a
timestamped `.bak` next to it, and the uninstaller only removes hook entries
carrying our marker — if you added hooks of your own, they stay.

Kill only what you want gone: a colleague who wants the per-message rules but
not the skill runs the gate uninstall; one who wants neither runs the first
command.

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
