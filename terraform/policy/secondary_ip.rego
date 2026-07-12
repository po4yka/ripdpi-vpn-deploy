package terraform.policy.secondary_ip

# no_secondary_public_ip_without_opt_in
#
# Deny a server resource that will have more than one public network interface
# unless the plan's variables include additional_public_ip = true.
#
# Provider mappings:
#   upcloud_server  — network_interface blocks with type = "public"
#   hcloud_server   — always has one public_net block; a floating IP resource
#                     (hcloud_floating_ip) is the secondary; detected via
#                     vultr_instance_ipv4 / vultr_instance resources below.
#   vultr_instance  — secondary detected via vultr_instance_ipv4 resource.
#   scaleway_instance_server — secondary detected by the dedicated
#                              scaleway_instance_ip.honeypot_ipv4 address.

opt_in := input.variables.additional_public_ip.value == true

# upcloud_server: count public network_interface blocks
deny[msg] {
  not opt_in
  rc := input.resource_changes[_]
  rc.type == "upcloud_server"
  after := rc.change.after

  public_ifaces := [ni |
    ni := after.network_interface[_]
    ni.type == "public"
  ]
  count(public_ifaces) > 1

  msg := sprintf(
    "resource %q: has %d public network interfaces; set additional_public_ip = true to allow a secondary public IP",
    [rc.address, count(public_ifaces)],
  )
}

# scaleway_instance_server: detect the dedicated honeypot routed IPv4 resource.
deny[msg] {
  not opt_in
  rc := input.resource_changes[_]
  rc.type == "scaleway_instance_ip"
  startswith(rc.address, "scaleway_instance_ip.honeypot_ipv4")
  rc.change.actions[_] == "create"

  msg := sprintf(
    "resource %q: allocating a secondary public IP (scaleway_instance_ip.honeypot_ipv4) requires additional_public_ip = true",
    [rc.address],
  )
}

# hcloud_server: detect companion hcloud_floating_ip resource being added
deny[msg] {
  not opt_in
  rc := input.resource_changes[_]
  rc.type == "hcloud_floating_ip"
  rc.change.actions[_] == "create"

  msg := sprintf(
    "resource %q: allocating a secondary public IP (hcloud_floating_ip) requires additional_public_ip = true",
    [rc.address],
  )
}

# vultr_instance: detect companion vultr_instance_ipv4 resource being added
deny[msg] {
  not opt_in
  rc := input.resource_changes[_]
  rc.type == "vultr_instance_ipv4"
  rc.change.actions[_] == "create"

  msg := sprintf(
    "resource %q: allocating a secondary public IP (vultr_instance_ipv4) requires additional_public_ip = true",
    [rc.address],
  )
}
