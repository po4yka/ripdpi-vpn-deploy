variable "exception_confirmation" {
  type        = string
  description = "Literal acknowledgement required even for an inert exception-root plan."
  sensitive   = true

  validation {
    condition     = var.exception_confirmation == "I_ACKNOWLEDGE_RU_CASCADE_JURISDICTION_EXCEPTION"
    error_message = "exception_confirmation must use the exact jurisdiction-exception acknowledgement literal."
  }
}

variable "activation_mode" {
  type        = string
  default     = "INERT_UNATTESTED"
  description = "The scaffold has exactly one allowed mode until governance is explicitly reversed."

  validation {
    condition     = var.activation_mode == "INERT_UNATTESTED"
    error_message = "Only INERT_UNATTESTED is permitted by the current governance decision."
  }
}

variable "attestation_file" {
  type        = string
  default     = ""
  description = "Optional absolute path to the non-secret candidate attestation."
}

variable "admin_user" {
  type        = string
  default     = "deploy"
  description = "Future provider-neutral inventory contract value."
}

variable "server_name" {
  type        = string
  default     = "cascade-candidate-inert"
  description = "Non-routable technical label for the inert scaffold."
}
