@AGENTS.md

## Claude Code

`AGENTS.md` above is the canonical project guidance for every agent; keep this file to Claude-specific additions. `.claude/settings.json` backs two of its rules: commit and PR attribution are disabled, and Claude's file-reading tools are denied every file inside the local operator kit's subdirectories (`secrets/local/*/`), its `README.md` and its dot files, which leaves the top-level `catalog.json` index readable; keep any other secret material out of the kit's top level. They are also denied `.env`, `*.tfstate`, decrypted secrets files (`*.secrets.yaml`, `*.secrets.yml`, `*.sops.yaml.dec`, `*.sops.json.dec`), and blue-green's temporary secrets directory. The deny list matches file names, so it misses a custom `VPN_SECRETS_FILE` path with another name, and it does not cover every shell or subprocess read, so the plaintext-secrets hard rule still applies to all commands.
