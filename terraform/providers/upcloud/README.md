# UpCloud provider

Terraform root for a single UpCloud VPS running the provider-neutral
Ansible stack.

Credentials come from `UPCLOUD_USERNAME` and `UPCLOUD_PASSWORD`; do not
place provider tokens in tfvars. The root exports the same
inventory-facing outputs as `providers/hetzner/` and `providers/vultr/`:

- `server_ipv4`
- `server_ipv6`
- `honeypot_ipv4`
- `admin_user`
- `server_hostname`
- `zone`

Example:

```bash
cp terraform/providers/upcloud/environments/prod.tfvars.example \
   terraform/providers/upcloud/environments/prod.tfvars
$EDITOR terraform/providers/upcloud/environments/prod.tfvars
UPCLOUD_USERNAME=... UPCLOUD_PASSWORD=... make PROVIDER=upcloud ENV=prod init plan
```

See `terraform/providers/upcloud/CLAUDE.md` for design decisions and pitfalls.

## Existing-node firewall activation

The server explicitly enables the provider firewall. DNS reply rules accept
TCP/UDP source port 53 only from `dns_resolver_ipv4s`, to the primary public
IPv4 and `dns_reply_port_range`. The defaults are UpCloud's IPv4 resolvers and
ports 32768–60999; verify the guest resolver and DNS client source-port policy,
because not every client uses that kernel range. IPv6 DNS replies are excluded.

Terraform updates the server before its dependent rules. Before enabling an
existing disabled firewall, preinstall and verify approved SSH and DNS rules,
then separately authorize an activation-only plan without replacement or
unrelated changes. Targeting the rules with `-target` still includes the server
dependency and is not a safe ordering workaround. A source merge does not
authorize live activation.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.15, < 2.0 |
| <a name="requirement_upcloud"></a> [upcloud](#requirement\_upcloud) | ~> 5.36 |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [terraform_data.ssh_port](https://registry.terraform.io/providers/hashicorp/terraform/latest/docs/resources/data) | resource |
| [upcloud_firewall_rules.vpn](https://registry.terraform.io/providers/UpCloudLtd/upcloud/latest/docs/resources/firewall_rules) | resource |
| [upcloud_server.vpn](https://registry.terraform.io/providers/UpCloudLtd/upcloud/latest/docs/resources/server) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_additional_public_ip"></a> [additional\_public\_ip](#input\_additional\_public\_ip) | Allocate a second public IPv4 to this server. Used by the honeypot<br/>role (vpn.enable\_honeypot) so the canary listener can bind to an IP<br/>that has no other service on it, separating its probe traffic from<br/>the real REALITY listener at the IP-reputation level. Off by default. | `bool` | `false` | no |
| <a name="input_admin_ssh_public_key"></a> [admin\_ssh\_public\_key](#input\_admin\_ssh\_public\_key) | Public SSH key only. The matching private key stays outside this repo. | `string` | n/a | yes |
| <a name="input_admin_user"></a> [admin\_user](#input\_admin\_user) | Non-root user created by cloud-init for SSH and Ansible access. | `string` | `"deploy"` | no |
| <a name="input_allowed_ssh_cidrs"></a> [allowed\_ssh\_cidrs](#input\_allowed\_ssh\_cidrs) | Source CIDRs allowed to reach ssh\_port/tcp. | `list(string)` | n/a | yes |
| <a name="input_build_env"></a> [build\_env](#input\_build\_env) | Free-form label baked into /etc/vpn-build-id by cloud-init. | `string` | `"prod"` | no |
| <a name="input_dns_reply_port_range"></a> [dns\_reply\_port\_range](#input\_dns\_reply\_port\_range) | Guest ephemeral destination ports allowed for replies from approved DNS resolvers. Verify the guest and DNS client source-port policy before activation; this default is not universal. | <pre>object({<br/>    start = number<br/>    end   = number<br/>  })</pre> | <pre>{<br/>  "end": 60999,<br/>  "start": 32768<br/>}</pre> | no |
| <a name="input_dns_resolver_ipv4s"></a> [dns\_resolver\_ipv4s](#input\_dns\_resolver\_ipv4s) | Approved DNS resolver IPv4 literals whose TCP/UDP replies may reach the primary public IPv4. Defaults are UpCloud's DNS resolvers; keep aligned with guest resolver configuration. | `list(string)` | <pre>[<br/>  "94.237.127.9",<br/>  "94.237.40.9"<br/>]</pre> | no |
| <a name="input_enable_backups"></a> [enable\_backups](#input\_enable\_backups) | Enable provider-side server backups (daily, 7-day retention). | `bool` | `true` | no |
| <a name="input_enable_hysteria"></a> [enable\_hysteria](#input\_enable\_hysteria) | Include the Hysteria2 UDP/443 listener in the legacy default set. Explicit public\_listeners ignore this toggle; add hysteria there directly. | `bool` | `true` | no |
| <a name="input_enable_ipv6"></a> [enable\_ipv6](#input\_enable\_ipv6) | Allocate and expose a public IPv6 address. | `bool` | `true` | no |
| <a name="input_labels"></a> [labels](#input\_labels) | Provider-specific resource tags/labels. | `map(string)` | `{}` | no |
| <a name="input_nginx_xhttp_public_port"></a> [nginx\_xhttp\_public\_port](#input\_nginx\_xhttp\_public\_port) | Public TCP port for nginx-xhttp. Keep this in sync with Ansible nginx\_xhttp\_public\_port. | `number` | `8443` | no |
| <a name="input_plan"></a> [plan](#input\_plan) | UpCloud plan slug, e.g. 1xCPU-2GB or DEV-2xCPU-4GB. | `string` | n/a | yes |
| <a name="input_public_listeners"></a> [public\_listeners](#input\_public\_listeners) | Public TCP/UDP listeners allowed at the provider edge. Specify exactly one of port or port\_range for each entry. | <pre>list(object({<br/>    name       = string<br/>    protocol   = string<br/>    port       = optional(number)<br/>    port_range = optional(string)<br/>  }))</pre> | `[]` | no |
| <a name="input_server_name"></a> [server\_name](#input\_server\_name) | Hostname / Terraform name of the VPS. | `string` | n/a | yes |
| <a name="input_ssh_port"></a> [ssh\_port](#input\_ssh\_port) | Effective SSH listener port configured by cloud-init and opened at the provider edge. | `number` | `22` | no |
| <a name="input_storage_size_gb"></a> [storage\_size\_gb](#input\_storage\_size\_gb) | Root disk size in GB. | `number` | `25` | no |
| <a name="input_storage_template"></a> [storage\_template](#input\_storage\_template) | Storage template UUID to clone from. Pin to a specific Debian 13 / Ubuntu 24.04 template. | `string` | n/a | yes |
| <a name="input_use_legacy_public_listeners"></a> [use\_legacy\_public\_listeners](#input\_use\_legacy\_public\_listeners) | Opt-in to the historical implicit listener set when public\_listeners is empty. New environments must define public\_listeners explicitly; an empty effective contract fails the plan. | `bool` | `false` | no |
| <a name="input_zone"></a> [zone](#input\_zone) | UpCloud zone. Allowed: fi-hel1 (Helsinki), de-fra1 (Frankfurt), nl-ams1 (Amsterdam), sg-sin1 (Singapore). | `string` | n/a | yes |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_admin_user"></a> [admin\_user](#output\_admin\_user) | n/a |
| <a name="output_honeypot_ipv4"></a> [honeypot\_ipv4](#output\_honeypot\_ipv4) | Secondary public IPv4 used by the honeypot when additional\_public\_ip = true. Null when not allocated. |
| <a name="output_public_listeners"></a> [public\_listeners](#output\_public\_listeners) | Canonical public listener contract enforced by the provider firewall. |
| <a name="output_server_hostname"></a> [server\_hostname](#output\_server\_hostname) | n/a |
| <a name="output_server_ipv4"></a> [server\_ipv4](#output\_server\_ipv4) | Public IPv4 address (primary). |
| <a name="output_server_ipv6"></a> [server\_ipv6](#output\_server\_ipv6) | Public IPv6 address (may be null if disabled). |
| <a name="output_ssh_port"></a> [ssh\_port](#output\_ssh\_port) | Effective SSH listener port. |
| <a name="output_zone"></a> [zone](#output\_zone) | Provider-specific zone/region/location identifier. |
<!-- END_TF_DOCS -->
