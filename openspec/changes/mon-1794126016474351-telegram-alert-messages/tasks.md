# MON-1794126016474351: Make Telegram alert messages readable and actionable

## Objective

Telegram alert messages show what failed, where, since when and what to check first.

## Ownership

One writer owns the `observability_control_plane` relay and rule templates, their tests and snapshots, `scripts/observability-operator.py` drill annotations, and the operator documentation in this change.

## Execution

- [x] MON-1794126893076662 Render structured relay messages from rule action, value and runbook annotations #feature @item:MON-1794126016474351
- [x] MON-1794127442259762 Document the Kuma Telegram template and monitor descriptions #feature @item:MON-1794126016474351

## Verification

Local: focused pytest, promtool rule cases, snapshot check, documentation check, role Molecule scenario and `make check`. Remote CI runs on the pull request. Dry-run, staging and live delivery need separate deployment authorization.
- [x] MON-1794135984867252 Tolerate one missed Kuma producer run without a notification #feature @item:MON-1794126016474351
