# attestations — non-secret expiring gate records

## Design decisions

This directory contains only schema-validated dated claims and opaque evidence references. Missing records are intentional fail-closed states; raw measurements, endpoints, provider identities, commands, and network inventories remain outside the repo.

## What's done well

- Candidate-ASN and per-leg health records have independent schemas and validators.
- No pending or synthetic record can be mistaken for a pass because no default JSON artifact is checked in.

## Pitfalls

- Never extend a date or copy an earlier result without a new underlying measurement.
- Never commit a record merely to make a plan or converge test pass.
