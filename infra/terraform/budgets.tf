resource "aws_budgets_budget" "cost_guardrail" {
  name              = "rag-pipeline-monthly-budget"
  budget_type       = "COST"
  limit_amount      = "200" # Realistic for EKS dev (control plane alone is $73/mo)
  limit_unit        = "USD"
  time_unit         = "MONTHLY"

  # Alert 1: If actual spend hits 80% of $200
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["gopalpatwa@gmail.com"]
  }

  # Alert 2: If AWS forecasts you will exceed $200 by the end of the month
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = ["gopalpatwa@gmail.com"]
  }
}