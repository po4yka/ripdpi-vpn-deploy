## Context

See proposal.md. The first audit added review pauses, an environment check in
the deploy controller, and a signal mapping around the vpnd review prompt. This
change closes the remaining paths around those boundaries with the smallest
change at each owner.

## Goals / Non-Goals

- Goal: each defect gets a fix at its owner and a regression that fails on the
  parent commit.
- Non-goal: change Hetzner, Scaleway or UpCloud image handling. Their image
  arguments are not shown to update in place; the Vultr provider documents an
  in-place OS change.
- Non-goal: Scaleway SSH key reuse. No duplicate-key refusal is confirmed for
  that provider.
- Non-goal: deploy, apply or touch any host or provider.

## Decisions

- vpnd signals: an asynchronous guard installs event-loop handlers for SIGINT,
  SIGQUIT, SIGTERM and SIGHUP for the pipeline and its cleanup. The handler only
  records the first signal. The pipeline checks the record before each step and
  after the last step, and a recorded signal becomes an ordinary failure with
  `exit_code` 128 plus the signal number, so the existing cleanup boundary runs
  `make clean`. A step that fails while a signal is recorded reports the signal.
  The review prompt keeps its synchronous handler, because the event loop does
  not run while the prompt blocks.
  Rejected: cancel the running Make child. Cancellation kills only the direct
  Make process; a decrypt or Terraform child can continue and write plaintext
  after `make clean`. Terminal signals already reach the foreground child.
  Rejected: a `signal.signal` handler that raises. It raises inside the event
  loop, outside the command coroutine, and skips the cleanup boundary.
- Vultr OS: add `os_id` to `ignore_changes` and a postcondition
  `self.os_id == var.os_id`. Rejected: a `terraform_data` replace trigger
  alone. A new trigger resource does not replace an existing node when it is
  first created (checked with Terraform), so the first `os_id` edit on an
  existing node would still reinstall it.
- Verification plays: one task file, `playbooks/tasks/selected-env.yml`, holds
  the assertion that `rotate-credentials.yml` already uses, tagged `always`, as
  the first pre-task of the three plays. The recipes set `ENV=$(ENV)` because
  the default `ENV` is not exported to the recipe environment. The rotation play
  keeps its own assertion unchanged.
- Hetzner key: `hcloud_ssh_key.admin` gets `count` and a `moved` block from the
  unindexed address; a `data "hcloud_ssh_key"` reads the named key when
  `admin_ssh_key_name` is set, with a postcondition that compares the key type
  and body with `admin_ssh_public_key`. The server replace triggers keep the
  indexed key name and public key and add the public-key digest that the other
  roots use, so a key change still forces a refused replacement in both modes.
  An indexed trigger to an absent instance is valid, and a moved key causes no
  change (checked with Terraform).

## Risks / Trade-offs

- A SIGTERM sent only to vpnd waits for the running step to finish before
  cleanup. This keeps one process tree and no plaintext writer after cleanup.
- A second terminal interrupt during `make clean` reaches the cleanup child too.
  vpnd then reports the cleanup failure; the first audit's runbook recipe
  documents a manual `make clean`.
- A Vultr node whose tfvars names another `os_id` cannot plan until the tfvars
  match the node or the node is replaced.
