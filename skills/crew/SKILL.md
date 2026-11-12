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

The full rules — what counts as small, when to escalate, the reviewer table —
are in the running text on the page and in `npx -y @starixs/crew plan`.
Read what it prints and follow it.

## First use on a machine

The split works without setup. The per-message rules need one install:

```bash
npx -y @starixs/crew check          # says whether the hook is wired
npx -y @starixs/crew install --apply --with-gate
```

`install` without `--apply` prints what it would write and changes nothing.
It copies a plain-text `gate.py` and the rule texts into
`~/.local/share/starixs/` and wires the host hook (Claude Code's
`settings.json`, backed up first, or a Codex plugin the user trusts once in
`/hooks`). It never uploads anything.

If the user declines, run `plan` yourself at the start of each heavy task
instead — the rules still reach you, just on demand.

## Commands

```bash
npx -y @starixs/crew plan --tags type=engineering,steps=multi,risk=reversible,for=self
npx -y @starixs/crew --set "brain=X;executor=Y;review=Z;helpers=W"
npx -y @starixs/crew --set none      # this host: no suggestion, work on current setup
npx -y @starixs/crew --off           # stop the note; the rules still apply
npx -y @starixs/crew --on
```

`plan` prints nothing for light work. That is correct — do not force it.

`--set` only after the user agrees. A split pinned for one host is never applied
to another.

## Before you say it is done

Say what verification ran and what it showed, and name what you did not verify.
**Work that cannot be run is not small.** If nothing could be verified, say so in
one line instead of calling it done.

Leave out how the work was divided unless the user asks.
