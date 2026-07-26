# Vultr provider

Terraform root for a single Vultr VPS running the provider-neutral Ansible
stack.

The Vultr provider requires `api_key` in the Terraform provider config. This
root wires it through the sensitive `vultr_api_key` variable; prefer exporting
`TF_VAR_vultr_api_key` instead of writing tokens into tfvars.

Keep that variable in an ignored local environment file or the operator's
secret store, with local-file mode `0600`. When API access is restricted by an
allowlist, add the current operator egress address before planning. After a
key replacement, run a scoped `make PROVIDER=vultr ENV=<environment> plan`
before revoking the prior key. Never pass a key on the command line or commit
it to this repository.

The root exports the same inventory-facing outputs as `providers/upcloud/`:

- `server_ipv4`
- `server_ipv6`
- `honeypot_ipv4`
- `admin_user`
- `server_hostname`
- `zone`

Example:

```bash
cp terraform/providers/vultr/environments/prod.tfvars.example \
   terraform/providers/vultr/environments/prod.tfvars
$EDITOR terraform/providers/vultr/environments/prod.tfvars
TF_VAR_vultr_api_key=... make PROVIDER=vultr ENV=prod init plan
```

See `terraform/providers/vultr/CLAUDE.md` for design decisions and pitfalls.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.15, < 2.0 |
| <a name="requirement_vultr"></a> [vultr](#requirement\_vultr) | ~> 2.31 |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [terraform_data.ssh_port](https://registry.terraform.io/providers/hashicorp/terraform/latest/docs/resources/data) | resource |
| [vultr_firewall_group.vpn](https://registry.terraform.io/providers/vultr/vultr/latest/docs/resources/firewall_group) | resource |
| [vultr_firewall_rule.icmp](https://registry.terraform.io/providers/vultr/vultr/latest/docs/resources/firewall_rule) | resource |
| [vultr_firewall_rule.ssh](https://registry.terraform.io/providers/vultr/vultr/latest/docs/resources/firewall_rule) | resource |
| [vultr_firewall_rule.tcp_public](https://registry.terraform.io/providers/vultr/vultr/latest/docs/resources/firewall_rule) | resource |
| [vultr_instance.vpn](https://registry.terraform.io/providers/vultr/vultr/latest/docs/resources/instance) | resource |
| [vultr_instance_ipv4.honeypot](https://registry.terraform.io/providers/vultr/vultr/latest/docs/resources/instance_ipv4) | resource |
| [vultr_ssh_key.admin](https://registry.terraform.io/providers/vultr/vultr/latest/docs/resources/ssh_key) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_additional_public_ip"></a> [additional\_public\_ip](#input\_additional\_public\_ip) | Allocate a second public IPv4 to this server. Used by the honeypot<br/>role (vpn.enable\_honeypot) so the canary listener can bind to an IP<br/>that has no other service on it, separating its probe traffic from<br/>the real REALITY listener at the IP-reputation level. Off by default. | `bool` | `false` | no |
| <a name="input_admin_ssh_public_key"></a> [admin\_ssh\_public\_key](#input\_admin\_ssh\_public\_key) | Public SSH key only. The matching private key stays outside this repo. | `string` | n/a | yes |
| <a name="input_admin_user"></a> [admin\_user](#input\_admin\_user) | Non-root user created by cloud-init for SSH and Ansible access. | `string` | `"deploy"` | no |
| <a name="input_allowed_ssh_cidrs"></a> [allowed\_ssh\_cidrs](#input\_allowed\_ssh\_cidrs) | Source CIDRs allowed to reach ssh\_port/tcp. | `list(string)` | n/a | yes |
| <a name="input_build_env"></a> [build\_env](#input\_build\_env) | Free-form label baked into /etc/vpn-build-id by cloud-init. | `string` | `"prod"` | no |
| <a name="input_enable_backups"></a> [enable\_backups](#input\_enable\_backups) | Enable provider-side server backups. Off by default: Vultr snapshots are unencrypted and bypass the restic+age backup chain. | `bool` | `false` | no |
| <a name="input_enable_hysteria"></a> [enable\_hysteria](#input\_enable\_hysteria) | n/a | `bool` | `true` | no |
| <a name="input_enable_ipv6"></a> [enable\_ipv6](#input\_enable\_ipv6) | Allocate and expose a public IPv6 address. | `bool` | `true` | no |
| <a name="input_labels"></a> [labels](#input\_labels) | Provider-specific resource tags/labels. | `map(string)` | `{}` | no |
| <a name="input_nginx_xhttp_public_port"></a> [nginx\_xhttp\_public\_port](#input\_nginx\_xhttp\_public\_port) | Public TCP port for nginx-xhttp. Keep this in sync with Ansible nginx\_xhttp\_public\_port. | `number` | `8443` | no |
| <a name="input_os_id"></a> [os\_id](#input\_os\_id) | Vultr OS id, e.g. Debian or Ubuntu image id from `vultr-cli os list`. | `number` | n/a | yes |
| <a name="input_plan"></a> [plan](#input\_plan) | Vultr plan slug, e.g. vc2-1c-1gb or vhf-1c-1gb. | `string` | n/a | yes |
| <a name="input_public_listeners"></a> [public\_listeners](#input\_public\_listeners) | Public TCP/UDP listeners allowed at the provider edge. Specify exactly one of port or port\_range for each entry. | <pre>list(object({<br/>    name       = string<br/>    protocol   = string<br/>    port       = optional(number)<br/>    port_range = optional(string)<br/>  }))</pre> | `[]` | no |
| <a name="input_region"></a> [region](#input\_region) | Vultr region, e.g. ams, fra, lhr, ewr. | `string` | n/a | yes |
| <a name="input_server_name"></a> [server\_name](#input\_server\_name) | Hostname / Terraform name of the VPS. | `string` | n/a | yes |
| <a name="input_ssh_port"></a> [ssh\_port](#input\_ssh\_port) | Effective SSH listener port configured by cloud-init and opened at the provider edge. | `number` | `22` | no |
| <a name="input_vultr_api_key"></a> [vultr\_api\_key](#input\_vultr\_api\_key) | Vultr API key. Prefer TF\_VAR\_vultr\_api\_key in the operator environment. | `string` | n/a | yes |

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
