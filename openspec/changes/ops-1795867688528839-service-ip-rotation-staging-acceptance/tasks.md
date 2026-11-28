# OPS-1795867688528839

## Objective

One disposable staging node and one real device complete the documented service IPv4 rotation cycle.

## Ownership

Operator acceptance run and evidence records only; no source change. One writer.

## Verification

Dry-run, staging and client evidence at the recorded source revision, then cleanup evidence.

## Execution

- [ ] OPS-1795867789913124 Run the dry-run, attach, refresh and retire cycle on a disposable staging node with one client device and record the evidence #chore @item:OPS-1795867688528839
- [ ] OPS-1795867836098156 Retire the disposable node and its addresses through the cleanup workflow #chore @item:OPS-1795867688528839
