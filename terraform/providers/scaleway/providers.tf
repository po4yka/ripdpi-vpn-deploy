provider "scaleway" {
  zone = var.zone

  # Credentials and project identity come from the operator environment:
  # SCW_ACCESS_KEY, SCW_SECRET_KEY, and SCW_DEFAULT_PROJECT_ID.
}
