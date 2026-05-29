# vpnd

Convenience CLI for [vpn-deploy](../).

`vpnd` is a Rust front door that wraps the existing `Makefile`, Terraform
roots, Ansible playbooks, and SOPS-encrypted secrets. The Makefile and
`scripts/` keep working unchanged — `vpnd` does not replace them.

Subcommand definitions: [`vpnd/src/cli.rs`](src/cli.rs). Design decisions: [`vpnd/CLAUDE.md`](CLAUDE.md).

## Build

```bash
cd vpnd
cargo build --release
./target/release/vpnd --help
```

## Use

```bash
vpnd deploy                       # guided wizard
vpnd deploy --explain             # print the underlying shell calls and exit
vpnd reconverge --env prod        # idempotent re-deploy
vpnd share phone --qr             # bundled recipient handoff
vpnd doctor --host prod --ai      # diagnostic bundle as AI-ready prompt
vpnd probe --profile p0           # profile-aware probing
vpnd preflight                    # pre-deploy guards
vpnd host list                    # local host registry
vpnd ai-docs [--out DIR]          # emit repo docs as structured markdown for AI context (default: ./ai-docs/)
```

## `--explain`

Every subcommand accepts `--explain`. It prints the exact shell
invocations `vpnd` would run, in order, then exits without running them.
The intent is for operators to learn (and audit) the underlying Make
targets without trusting the binary blindly.

## Man page

A man page is generated at build time via `clap_mangen` and written to
`target/man/vpnd.1`. To install it system-wide:

```bash
cargo build --release
sudo install -m 644 target/man/vpnd.1 /usr/local/share/man/man1/vpnd.1
man vpnd
```

## Working directory

`vpnd` expects to be run from the repo root (it discovers `Makefile`,
`ansible/`, `terraform/` relative to the cwd) or with `VPN_DEPLOY_ROOT`
set in the environment.
