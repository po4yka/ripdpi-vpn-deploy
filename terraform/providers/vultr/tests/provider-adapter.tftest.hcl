# Canonical listeners stay provider-neutral; API port ranges use Vultr syntax.
mock_provider "vultr" {}

variables {
  server_name          = "vpn-adapter-test"
  region               = "ams"
  plan                 = "vc2-1c-1gb"
  os_id                = 2136
  admin_ssh_public_key = "ssh-ed25519 AAAATESTKEY test@harness"
  allowed_ssh_cidrs    = ["203.0.113.42/32"]
  build_env            = "test"
  public_listeners = [
    { name = "tcp-window", protocol = "tcp", port_range = "4433-4443" },
    { name = "udp-window", protocol = "udp", port_range = "51820-51822" },
    { name = "tcp-single", protocol = "tcp", port = 443 },
    { name = "udp-single", protocol = "udp", port = 443 },
  ]
}

run "ranges_are_adapted_without_changing_listener_contract" {
  command = plan

  assert {
    condition = alltrue([
      for family in ["v4", "v6"] :
      vultr_firewall_rule.tcp_public["${family}-tcp-4433-4443"].port == "4433:4443" &&
      vultr_firewall_rule.tcp_public["${family}-tcp-4433-4443"].ip_type == family &&
      vultr_firewall_rule.tcp_public["${family}-tcp-4433-4443"].protocol == "tcp" &&
      vultr_firewall_rule.tcp_public["${family}-udp-51820-51822"].port == "51820:51822" &&
      vultr_firewall_rule.tcp_public["${family}-udp-51820-51822"].ip_type == family &&
      vultr_firewall_rule.tcp_public["${family}-udp-51820-51822"].protocol == "udp" &&
      vultr_firewall_rule.tcp_public["${family}-tcp-443"].port == "443" &&
      vultr_firewall_rule.tcp_public["${family}-udp-443"].port == "443"
    ]) && length(vultr_firewall_rule.tcp_public) == 8
    error_message = "Both address families must use colon ranges, stable canonical keys and unchanged singleton ports."
  }

  assert {
    condition     = output.public_listeners == var.public_listeners
    error_message = "The exported listener contract must preserve canonical hyphen ranges and singleton ports."
  }
}

run "enabled_backups_have_one_daily_schedule" {
  command = plan

  variables {
    enable_backups = true
  }

  assert {
    condition = (
      vultr_instance.vpn.backups == "enabled" &&
      length(vultr_instance.vpn.backups_schedule) == 1 &&
      vultr_instance.vpn.backups_schedule[0].type == "daily" &&
      vultr_instance.vpn.backups_schedule[0].hour == 3
    )
    error_message = "Enabled Vultr backups require one daily schedule at 03:00 UTC."
  }
}

run "disabled_backups_have_no_schedule" {
  command = plan

  variables {
    enable_backups = false
  }

  assert {
    condition     = vultr_instance.vpn.backups == "disabled" && length(vultr_instance.vpn.backups_schedule) == 0
    error_message = "Disabled Vultr backups must not retain a schedule block."
  }
}
