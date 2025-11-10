variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "elevenlabs_api_key" {
  description = "ElevenLabs API key"
  type        = string
  sensitive   = true
}

variable "deepgram_api_key" {
  description = "Deepgram API key"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "twilio_account_sid" {
  description = "Twilio Account SID"
  type        = string
  sensitive   = true
}

variable "twilio_auth_token" {
  description = "Twilio Auth Token"
  type        = string
  sensitive   = true
}

variable "acm_certificate_arn" {
  description = "ARN of an existing ACM certificate"
  type        = string
}

variable "custom_domain" {
  description = "Custom domain for the application (optional)"
  type        = string
  default     = ""
}

variable "mailersend_api_key" {
  description = "Mailersend API key"
  type        = string
  default     = ""
}

variable "mailersend_from_email" {
  description = "Mailersend from url"
  type        = string
  default     = ""
}

variable "decisionrules_solver_key" {
  description = "DecisionRules solver key"
  type        = string
  default     = ""
}

variable "decisionrules_host" {
  description = "DecisionRules host"
  type        = string
  default     = ""
}

variable "decisionrules_rule_alias" {
  description = "DecisionRules rule alias"
  type        = string
  default     = ""
}

variable "decisionrules_rule_id" {
  description = "DecisionRules rule id"
  type        = string
  default     = ""
}