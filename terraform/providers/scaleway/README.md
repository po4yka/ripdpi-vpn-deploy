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

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.15, < 2.0 |
| <a name="requirement_scaleway"></a> [scaleway](#requirement\_scaleway) | ~> 2.77 |

## Modules

No modules.

## Resources

| Name | Type |
| ---- | ---- |
| [scaleway_instance_ip.honeypot_ipv4](https://registry.terraform.io/providers/scaleway/scaleway/latest/docs/resources/instance_ip) | resource |
| [scaleway_instance_ip.ipv4](https://registry.terraform.io/providers/scaleway/scaleway/latest/docs/resources/instance_ip) | resource |
| [scaleway_instance_ip.ipv6](https://registry.terraform.io/providers/scaleway/scaleway/latest/docs/resources/instance_ip) | resource |
| [scaleway_instance_security_group.vpn](https://registry.terraform.io/providers/scaleway/scaleway/latest/docs/resources/instance_security_group) | resource |
| [scaleway_instance_server.vpn](https://registry.terraform.io/providers/scaleway/scaleway/latest/docs/resources/instance_server) | resource |
| [terraform_data.ssh_port](https://registry.terraform.io/providers/hashicorp/terraform/latest/docs/resources/data) | resource |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_additional_public_ip"></a> [additional\_public\_ip](#input\_additional\_public\_ip) | Allocate a second routed public IPv4 for the honeypot role. | `bool` | `false` | no |
| <a name="input_admin_ssh_public_key"></a> [admin\_ssh\_public\_key](#input\_admin\_ssh\_public\_key) | Public SSH key only. The matching private key stays outside this repo. | `string` | n/a | yes |
| <a name="input_admin_user"></a> [admin\_user](#input\_admin\_user) | Non-root user created by cloud-init for SSH and Ansible access. | `string` | `"deploy"` | no |
| <a name="input_allowed_ssh_cidrs"></a> [allowed\_ssh\_cidrs](#input\_allowed\_ssh\_cidrs) | Source CIDRs allowed to reach ssh\_port/tcp. | `list(string)` | n/a | yes |
| <a name="input_build_env"></a> [build\_env](#input\_build\_env) | Free-form label baked into /etc/vpn-build-id by cloud-init. | `string` | `"prod"` | no |
| <a name="input_enable_hysteria"></a> [enable\_hysteria](#input\_enable\_hysteria) | n/a | `bool` | `true` | no |
| <a name="input_enable_ipv6"></a> [enable\_ipv6](#input\_enable\_ipv6) | Allocate and expose a reserved routed public IPv6 address. | `bool` | `true` | no |
| <a name="input_image"></a> [image](#input\_image) | Scaleway Marketplace image label. | `string` | `"ubuntu_noble"` | no |
| <a name="input_labels"></a> [labels](#input\_labels) | Provider-specific resource tags/labels. | `map(string)` | `{}` | no |
| <a name="input_nginx_xhttp_public_port"></a> [nginx\_xhttp\_public\_port](#input\_nginx\_xhttp\_public\_port) | Public TCP port for nginx-xhttp. Keep this in sync with Ansible nginx\_xhttp\_public\_port. | `number` | `8443` | no |
| <a name="input_public_listeners"></a> [public\_listeners](#input\_public\_listeners) | Public TCP/UDP listeners allowed at the provider edge. Specify exactly one of port or port\_range for each entry. | <pre>list(object({<br/>    name       = string<br/>    protocol   = string<br/>    port       = optional(number)<br/>    port_range = optional(string)<br/>  }))</pre> | `[]` | no |
| <a name="input_server_name"></a> [server\_name](#input\_server\_name) | Hostname / Terraform name of the VPS. | `string` | n/a | yes |
| <a name="input_server_type"></a> [server\_type](#input\_server\_type) | Scaleway Instance commercial type. | `string` | n/a | yes |
| <a name="input_ssh_port"></a> [ssh\_port](#input\_ssh\_port) | Effective SSH listener port configured by cloud-init and opened at the provider edge. | `number` | `22` | no |
| <a name="input_zone"></a> [zone](#input\_zone) | Scaleway Availability Zone. | `string` | n/a | yes |

## Outputs

| Name | Description |
| ---- | ----------- |
| <a name="output_admin_user"></a> [admin\_user](#output\_admin\_user) | n/a |
| <a name="output_honeypot_ipv4"></a> [honeypot\_ipv4](#output\_honeypot\_ipv4) | Secondary routed public IPv4 used by the honeypot when additional\_public\_ip = true. |
| <a name="output_public_listeners"></a> [public\_listeners](#output\_public\_listeners) | Canonical public listener contract enforced by the provider security group. |
| <a name="output_server_hostname"></a> [server\_hostname](#output\_server\_hostname) | n/a |
| <a name="output_server_ipv4"></a> [server\_ipv4](#output\_server\_ipv4) | Public IPv4 address (primary). |
| <a name="output_server_ipv6"></a> [server\_ipv6](#output\_server\_ipv6) | Public IPv6 address (may be null if disabled). |
| <a name="output_ssh_port"></a> [ssh\_port](#output\_ssh\_port) | Effective SSH listener port. |
| <a name="output_zone"></a> [zone](#output\_zone) | Scaleway Availability Zone. |
<!-- END_TF_DOCS -->
