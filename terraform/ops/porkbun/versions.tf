terraform {
  required_version = "1.13.10"

  required_providers {
    # Vetted community provider, pinned to one exact release
    # (docs/research/porkbun-provider-vetting-2026-11.md).
    porkbun = {
      source  = "marcfrederick/porkbun"
      version = "1.3.3"
    }
  }
}
