provider "vultr" {
  # The provider also recognizes VULTR_API_KEY internally, but its Terraform
  # schema marks api_key as required, so wire it through a sensitive variable.
  # Prefer TF_VAR_vultr_api_key in the operator environment.
  api_key = var.vultr_api_key
}
