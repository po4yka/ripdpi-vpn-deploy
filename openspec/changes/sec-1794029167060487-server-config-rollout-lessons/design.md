# Design

## Self-steal certificate series

The agent role checks the installed self-steal leaf certificate on the host (`stat`, read-only, also in check mode). It loads the credential only when that certificate exists, so the profile no longer carries a hand-set flag. A capability gauge exported with the series lets the control plane alert when self-steal is installed but no expiry series arrives.

## Observer firewall ownership

`scripts/tailnet_firewall.py` `foundation()` is the only renderer of the observer's `/etc/nftables.conf`. Rules added by hand on top would be lost when the foundation is applied again. The foundation therefore renders the observer private-ingress rule and, only in Telegram mode, the docker0 forward accepts for the provider resolvers and the Telegram API network, plus the return path. All of them use validated inputs and are off by default.

## Operator diagnostics

A failing Ansible run records only the bounded `TASK [...]` header of the failing task and the host alias. Task output and module arguments are never recorded. Lock contention and a missing generated inventory become typed refusals; lock semantics are unchanged.
