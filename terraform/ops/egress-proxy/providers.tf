provider "hcloud" {
  # Credentials come from environment variables - never put them in tfvars or state.
  #   HCLOUD_TOKEN
  # Use a dedicated project token with only the rights this stack needs.
}
