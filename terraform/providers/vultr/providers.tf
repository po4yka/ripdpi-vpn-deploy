provider "vultr" {
  # Credentials come from the environment — never put them in tfvars or state.
  #   VULTR_API_KEY
  # The provider schema marks api_key as required but fills it from
  # VULTR_API_KEY via EnvDefaultFunc, so an empty block is sufficient.
}
