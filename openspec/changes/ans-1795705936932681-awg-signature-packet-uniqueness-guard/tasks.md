# ANS-1795705936932681: Refuse AmneziaWG signature packets that repeat across nodes or match a public default

## Objective

Production generates the AmneziaWG signature packets per instance. It refuses a packet that is byte-identical on two nodes or equal to a publicly known upstream default.

## Ownership

`ansible/roles/amneziawg/` and `docs/reference/awg-cohorts.md`. Starts after both related changes merge. One writer.

## Verification

Planning: `./taskctl validate`, strict OpenSpec validation and `make docs-check`. Implementation: the narrow tests of the touched area, then `make check`. Staging: generated packets pass real peer traffic in the AWG staging lane.

## Execution

- [ ] ANS-1795705961986664 Generate signature packets per instance within the admitted bounds, with a test that two new instances differ #feature @item:ANS-1795705936932681
- [ ] ANS-1795705992908149 Add the production guard for repeated packets and public default digests, with refusal and staging tests #feature @item:ANS-1795705936932681
- [ ] ANS-1795706024137644 Update docs/reference/awg-cohorts.md with the guard and the data file rule #feature @item:ANS-1795705936932681
