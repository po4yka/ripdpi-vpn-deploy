# The observer has no public workload listeners and retains its own backup disk.
resource "upcloud_storage" "observer_backup" {
  count   = var.node_purpose == "observer" && var.observer_backup_size_gb == 10 ? 1 : 0
  zone    = var.zone
  title   = "${var.server_name}-observer-backup"
  size    = var.observer_backup_size_gb
  tier    = "hdd"
  encrypt = true
}
