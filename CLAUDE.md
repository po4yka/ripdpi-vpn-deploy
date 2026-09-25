@AGENTS.md

## Claude Code

`AGENTS.md` above is the canonical project guidance for every agent; keep this file to Claude-specific additions. `.claude/settings.json` backs two of its rules: commit and PR attribution are disabled, and Claude's file-reading tools are denied `.env`, `secrets/local/`, `*.tfstate`, decrypted secrets files (`*.secrets.yaml`, `*.secrets.yml`, `*.sops.yaml.dec`, `*.sops.json.dec`), and blue-green's temporary secrets directory. The deny list matches file names, so it misses a custom `VPN_SECRETS_FILE` path with another name, and it does not cover every shell or subprocess read, so the plaintext-secrets hard rule still applies to all commands.
