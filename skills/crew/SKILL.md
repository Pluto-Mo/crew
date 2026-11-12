---
name: crew
description: "Division of labour for heavy work: brain, hand, review, verify. Use when work is multi-step, touches several files or modules, or ends in something hard to undo (deploy, publish, delete, send, pay). Run it before starting, and again when a task that looked light turns out heavy. Not needed for chat, one-line answers, translation, naming, or a single small edit."
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

## How to run it

**Prefer a local copy.** If `scripts/starixs.py` exists next to this file, run it
directly — it is instant:

```bash
python3 <this-skill-dir>/scripts/starixs.py --tags type=engineering,steps=multi,risk=reversible,for=self
```

**Otherwise** fetch it once per session:

```bash
npx -y github:Pluto-Mo/crew plan --tags type=engineering,steps=multi,risk=reversible,for=self
```

That takes about seven seconds cold. Do it once and keep the output; do not call
it repeatedly in the same task.

`plan` prints the split rules for this task. It prints **nothing** for light
work — that is correct, do not force it.

## First use on a machine

The split works with no setup. The per-message rules need one install:

```bash
npx -y github:Pluto-Mo/crew check          # says whether the hook is wired
npx -y github:Pluto-Mo/crew install --apply --with-gate
```

`install` without `--apply` prints what it would write and changes nothing. It
copies a plain-text `gate.py` and the rule texts into `~/.local/share/starixs/`
and wires the host hook: Claude Code's `settings.json` (backed up first), or a
Codex plugin the user trusts once in `/hooks`. It never uploads anything.

If the user declines, run `plan` at the start of each heavy task instead — the
rules still reach you, just on demand.

## Pinning a split

Only after the user agrees. A split pinned for one host is never applied to
another.

```bash
<crew> --set "brain=X;executor=Y;review=Z;helpers=W"
<crew> --set none      # this host: no suggestion, work on the current setup
<crew> --off           # stop the note; the rules still apply
<crew> --on
```

## Before you say it is done

Say what verification ran and what it showed, and name what you did not verify.
**Work that cannot be run is not small.** If nothing could be verified, say so in
one line instead of calling it done.

Leave out how the work was divided unless the user asks.
