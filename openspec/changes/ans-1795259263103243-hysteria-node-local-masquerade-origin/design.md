## Context

Hysteria answers HTTP/3 on its UDP port and, with `hysteria_masquerade_tcp`, HTTPS on TCP/443 and HTTP on TCP/80. Its masquerade handler has three types: `proxy`, `file` and `string`. The role uses `proxy` today. `ANS-1795162466557355` builds a unique site bundle per operator and publishes it for the REALITY self-steal and nginx-xhttp frontends.

## Goals / Non-Goals

Goals: a node without a web frontend serves a site from its own disk; the site comes from the operator bundle and is unique per operator.

Non-goals: a new content generator, a web server beside Hysteria, changes to the bundle format.

## Decisions

- Use the Hysteria `file` type rather than a local nginx origin, because a second listener on the node adds a process and a port for no gain.
- Consume the published tree of the site bundle read-only; the bundle publisher stays the only writer.
- Keep the proxy origin as the fallback for nodes without a bundle, with the existing self-origin refusal.

## Contracts and ownership

The site bundle contract of `ANS-1795162466557355` stays unchanged. The Hysteria role owns only the masquerade selection and its admission.

## Risks / Trade-offs

- A scheduled bundle refresh replaces the tree while Hysteria serves it; the publisher must swap the directory atomically.
- The `file` type has no per-path rewrite, so the bundle must be a static tree.

## Migration Plan

Deploy with the bundle present; the role switches the origin on the next convergence. Rollback is the previous proxy origin in the profile.
