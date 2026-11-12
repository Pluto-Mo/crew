---
name: crew
description: "Division of labour for heavy work: brain, hand, review, verify. Use when work is multi-step, touches several files or modules, or ends in something hard to undo (deploy, publish, delete, send, pay). Run it before starting, and again when a task that looked light turns out heavy. Not needed for chat, one-line answers, translation, naming, or a single small edit. Also use it when the user says 更新 / 升级 / 有新版本吗 / update crew (update it), or 卸载 / 删除 / remove crew (remove it)."
allowed-tools: Bash
---

# crew

Heavy work runs as four jobs. One context being author, reviewer and judge at
once is how "done" becomes a claim instead of a fact.

| Job | Does | Must not |
|---|---|---|
| Brain | Decides the approach and the hard calls | Be consulted for a handful of steps |
| Hand | Does the work | Judge its own result |
| Review | Reads the result against the goal, fresh read-only context | Have done the work; be weaker than the hand |
| Verify | Runs something that can fail | Be replaced by a model's opinion |

## Updating it

When the user says 更新 / 升级 / 有新版本吗 / update / upgrade — do it, do not ask
whether they are sure:

```bash
npx -y skills add Pluto-Mo/crew --skill crew -g -y
python3 "$HOME/.agents/skills/crew/scripts/gate_install.py" --apply
python3 "$HOME/.agents/skills/crew/scripts/starixs.py" --version
```

The first line replaces the skill folder; the second brings the installed gate to
the same version; the third prints what you now have. Report that version number
in one line — that is the proof it went through, not "updated successfully".

`skills add` overwrites in place, so local edits to those files are lost. That is
by design: they are shipped files. The user's own settings live in
`~/.local/share/starixs` and are never touched by an update.

If the first command fails because the machine is offline, say so and stop — an
older gate keeps working, and the next run of `starixs.py` retries the gate
refresh on its own. Do not hand-edit files to fake a newer version.

Skip the second line if `gate_install.py --check` says no hook is installed:
there is nothing to refresh, and the skill is enough on its own.

## Set up once, the first time you read this

Run the check. If it says no hook is active, run the install, then check again:

```bash
python3 "$HOME/.agents/skills/crew/scripts/gate_install.py" --check
python3 "$HOME/.agents/skills/crew/scripts/gate_install.py" --apply
```

If that path does not exist, the skill lives elsewhere — find the folder holding
SKILL.md and use its `scripts/gate_install.py`. If there is no `scripts/` at all,
this copy shipped only the text; install the full one:

```bash
npx -y skills add Pluto-Mo/crew --skill crew -g -y
```

What it does: copies a plain-text `gate.py` and the rule texts to
`~/.local/share/starixs/`, then wires the host hook — Claude Code's
`settings.json` (backed up first) or a Codex plugin. Idempotent, writes nothing
outside those two places, uploads nothing. Undo: the same script with
`--uninstall`.

Report in one line what changed. Then mind these three:

- **Codex needs one trust click in `/hooks`.** Only a person can do that. Until
  `--check` says `hook active`, do not tell the user the rules are arriving with
  each message — say the hook is installed and they need to trust it once.
- **Sandboxed hosts may block writes to `$HOME`.** Say so and hand the user the
  command to run in their own terminal. Do not route around it.
- **If the user declines, drop it.** Run `plan` at the start of each heavy task
  instead; the rules still arrive, just on demand.

Once `--check` reports active, you never need this section again.

## How to run it

Run the local copy — it is instant:

```bash
python3 "$HOME/.agents/skills/crew/scripts/starixs.py" --tags type=engineering,steps=multi,risk=reversible,for=self
```

`--tags` is the task profile: `type`, `steps`, `risk`, `for`, and optionally
`shape`. `steps=multi` is what makes it print anything; light work prints nothing
and that is correct, do not force it.

The output is the split for this task: which jobs it needs, when to consult the
brain, what counts as small, the reviewer table, and the hand-off brief for any
subagent. Follow what it prints.

No local copy? Fetch once per session — about seven seconds cold, so keep the
output rather than calling it repeatedly:

```bash
npx -y github:Pluto-Mo/crew plan --tags type=engineering,steps=multi,risk=reversible,for=self
```

## Pinning a split

Only after the user agrees. A split pinned for one host is never applied to
another.

```bash
python3 "$HOME/.agents/skills/crew/scripts/starixs.py" --set "brain=X;executor=Y;review=Z;helpers=W"
python3 "$HOME/.agents/skills/crew/scripts/starixs.py" --set none   # no suggestion here
python3 "$HOME/.agents/skills/crew/scripts/starixs.py" --off        # stop the note; rules still apply
python3 "$HOME/.agents/skills/crew/scripts/starixs.py" --on
```


## Removing it

When the user says they want it gone — 卸载 / uninstall / 删掉 / remove this:

```bash
python3 "$HOME/.agents/skills/crew/scripts/gate_install.py" --uninstall --all
```

One command removes three things: the skill folder, the gate and rule texts in
`~/.local/share/starixs`, and the hook entries in the host config (backup taken
first). Nothing else is touched.

Variants, in case only part of it is unwanted:

| Command | Removes |
|---|---|
| `--uninstall` | the hook and gate files; keeps the record directory |
| `--uninstall --purge` | the above plus the record directory |
| `--uninstall --all` | all of the above plus the skill folder |

Run it from the copy inside the skill folder. If that path is gone, the hook can
still be removed from a fresh checkout: `python3 scripts/gate_install.py --uninstall`.

## Before you say it is done

Say what verification ran and what it showed, and name what you did not verify.
**Work that cannot be run is not small.** If nothing could be verified, say so in
one line instead of calling it done.

Leave out how the work was divided unless the user asks.
