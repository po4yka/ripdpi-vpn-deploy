# Scaleway provider

Terraform root for a single Scaleway Instance running the provider-neutral Ansible stack.

Credentials and project selection come from `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, and `SCW_DEFAULT_PROJECT_ID`; never place them in `*.tfvars`. The root exports the same inventory-facing outputs as the other provider roots.

```bash
cp terraform/providers/scaleway/environments/prod.tfvars.example terraform/providers/scaleway/environments/prod.tfvars
$EDITOR terraform/providers/scaleway/environments/prod.tfvars
SCW_ACCESS_KEY=... SCW_SECRET_KEY=... SCW_DEFAULT_PROJECT_ID=... make PROVIDER=scaleway ENV=prod init plan
```

Scaleway routed IPv4 and IPv6 addresses are explicit Terraform resources and are attached to the Instance through `ip_ids`. The security group is stateful, default-deny for inbound traffic, and generated from the shared typed `public_listeners` contract.

See `terraform/providers/scaleway/CLAUDE.md` for design decisions and pitfalls.
