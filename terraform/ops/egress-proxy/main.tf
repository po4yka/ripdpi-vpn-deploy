locals {
  user_data = templatefile("${path.module}/../../shared/cloud-init.yaml.tftpl", {
    admin_user                  = var.admin_user
    admin_ssh_public_keys       = var.admin_ssh_public_keys
    ssh_port                    = var.ssh_port
    build_env                   = var.build_env
    bootstrap_ssh_ownership_b64 = filebase64("${path.module}/../../shared/bootstrap-sshd-ownership.py")
  })

  base_labels = merge(var.labels, {
    managed_by = "terraform"
    env        = var.build_env
  })
}

resource "terraform_data" "ssh_port" {
  input = var.ssh_port
}

resource "terraform_data" "admin_user" {
  input = var.admin_user
}

resource "hcloud_ssh_key" "admin" {
  name       = "${var.server_name}-${var.admin_user}"
  public_key = var.admin_ssh_public_keys[0]
  labels     = local.base_labels
}

# Provider API allowlists name this address, so it outlives the server: a lost
# or replaced server reattaches it, and destroying the root needs an explicit
# override. auto_delete = false keeps it when the server is deleted.
resource "hcloud_primary_ip" "egress" {
  name        = "${var.server_name}-egress"
  location    = var.location
  type        = "ipv4"
  auto_delete = false
  labels      = local.base_labels

  lifecycle {
    prevent_destroy = true
  }
}

# Management SSH only. The proxy listens on the Tailnet address, and Tailscale
# needs no inbound rule, so nothing else is open at the provider edge.
resource "hcloud_firewall" "egress" {
  name   = "${var.server_name}-egress"
  labels = local.base_labels

  rule {
    direction   = "in"
    protocol    = "icmp"
    source_ips  = ["0.0.0.0/0", "::/0"]
    description = "ICMP"
  }

  dynamic "rule" {
    for_each = var.allowed_ssh_cidrs
    content {
      direction   = "in"
      protocol    = "tcp"
      port        = tostring(var.ssh_port)
      source_ips  = [rule.value]
      description = "SSH allow ${rule.value}"
    }
  }
}

resource "hcloud_server" "egress" {
  name        = var.server_name
  location    = var.location
  server_type = var.server_type
  image       = var.image

  firewall_ids = [hcloud_firewall.egress.id]

  ssh_keys  = [hcloud_ssh_key.admin.id]
  user_data = local.user_data
  labels    = local.base_labels

  public_net {
    ipv4_enabled = true
    ipv4         = hcloud_primary_ip.egress.id
    # IPv4 only: provider allowlists name one IPv4 address.
    ipv6_enabled = false
  }

  # The server is disposable; replacing it keeps the primary IP.
  lifecycle {
    replace_triggered_by = [
      terraform_data.ssh_port,
      terraform_data.admin_user,
      hcloud_ssh_key.admin.name,
      hcloud_ssh_key.admin.public_key,
    ]
    ignore_changes = [
      user_data,
    ]
  }
}
