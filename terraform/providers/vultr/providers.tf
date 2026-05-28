provider "vultr" {
  # Auth via VULTR_API_KEY env var (matches hetzner/upcloud pattern).
  # Never pass credentials through a TF variable — they would land in state.
}
