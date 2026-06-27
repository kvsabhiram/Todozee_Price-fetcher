# ─── Log groups ──────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "app" {
  name              = local.log_group_app
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "boot" {
  name              = local.log_group_boot
  retention_in_days = var.log_retention_days
}

# ─── Metric filters on the app log ───────────────────────────────────────────
# Counts the "ALL sources failed!" line emitted when every price source is down.
resource "aws_cloudwatch_log_metric_filter" "fetch_all_failed" {
  name           = "${var.project}-fetch-all-failed"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "\"ALL sources failed\""

  metric_transformation {
    name          = "FetchAllFailed"
    namespace     = local.metric_namespace
    value         = "1"
    default_value = "0"
  }
}

# Python tracebacks => the app crashed/threw unexpectedly.
resource "aws_cloudwatch_log_metric_filter" "app_errors" {
  name           = "${var.project}-app-errors"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "Traceback"

  metric_transformation {
    name          = "AppErrors"
    namespace     = local.metric_namespace
    value         = "1"
    default_value = "0"
  }
}

# Heartbeat: every successful save writes "Saved to rates.json".
resource "aws_cloudwatch_log_metric_filter" "fetch_success" {
  name           = "${var.project}-fetch-success"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "\"Saved to rates.json\""

  metric_transformation {
    name          = "FetchSuccess"
    namespace     = local.metric_namespace
    value         = "1"
    default_value = "0"
  }
}

# ─── SNS alerts ──────────────────────────────────────────────────────────────
resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  for_each  = toset(var.alert_emails)
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

# ─── Alarms ──────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "fetch_all_failed" {
  alarm_name          = "${var.project}-fetch-all-failed"
  alarm_description   = "All price sources failed on a fetch attempt."
  namespace           = local.metric_namespace
  metric_name         = "FetchAllFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "app_errors" {
  alarm_name          = "${var.project}-app-errors"
  alarm_description   = "Python traceback detected in the app log."
  namespace           = local.metric_namespace
  metric_name         = "AppErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ec2_status_check" {
  alarm_name          = "${var.project}-ec2-status-check"
  alarm_description   = "EC2 instance/system status check failed."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  # "missing" avoids a spurious ALARM during the first minutes after an instance
  # replace; a genuine failure still reports a datapoint of 1 and alarms.
  treat_missing_data = "missing"
  dimensions         = { InstanceId = aws_instance.app.id }
  alarm_actions      = [aws_sns_topic.alerts.arn]
  ok_actions         = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project}-cpu-high"
  alarm_description   = "CPU sustained above 80%."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { InstanceId = aws_instance.app.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# StatusCheckFailed_Instance recovery via EC2 auto-recover action.
resource "aws_cloudwatch_metric_alarm" "ec2_recover" {
  alarm_name          = "${var.project}-ec2-auto-recover"
  alarm_description   = "Recover the instance on system status check failure."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { InstanceId = aws_instance.app.id }
  alarm_actions       = ["arn:aws:automate:${var.region}:ec2:recover", aws_sns_topic.alerts.arn]
}

# ─── Dashboard ───────────────────────────────────────────────────────────────
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "Todozee-Price-Fetcher"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "text", x = 0, y = 0, width = 24, height = 2,
        properties = {
          markdown = "# Todozee Price Fetcher — ${var.domain}\nGold & Silver rate API · region ${var.region} · instance `${aws_instance.app.id}`"
        }
      },
      {
        type = "metric", x = 0, y = 2, width = 12, height = 6,
        properties = {
          title   = "Price fetches (success vs total-fail)"
          region  = var.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            [local.metric_namespace, "FetchSuccess", { label = "Successful saves", color = "#2ca02c" }],
            [local.metric_namespace, "FetchAllFailed", { label = "All-sources-failed", color = "#d62728" }],
            [local.metric_namespace, "AppErrors", { label = "Tracebacks", color = "#ff7f0e" }]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 2, width = 12, height = 6,
        properties = {
          title   = "CPU utilization"
          region  = var.region
          view    = "timeSeries"
          period  = 300
          metrics = [["AWS/EC2", "CPUUtilization", "InstanceId", aws_instance.app.id, { stat = "Average" }]]
        }
      },
      {
        type = "metric", x = 0, y = 8, width = 8, height = 6,
        properties = {
          title  = "Network (bytes)"
          region = var.region
          view   = "timeSeries"
          period = 300
          metrics = [
            ["AWS/EC2", "NetworkIn", "InstanceId", aws_instance.app.id, { stat = "Average", label = "In" }],
            ["AWS/EC2", "NetworkOut", "InstanceId", aws_instance.app.id, { stat = "Average", label = "Out" }]
          ]
        }
      },
      {
        type = "metric", x = 8, y = 8, width = 8, height = 6,
        properties = {
          title  = "Memory / Disk used %"
          region = var.region
          view   = "timeSeries"
          period = 300
          metrics = [
            ["CWAgent", "mem_used_percent", "InstanceId", aws_instance.app.id, { stat = "Average", label = "Memory %" }],
            ["CWAgent", "disk_used_percent", "InstanceId", aws_instance.app.id, "path", "/", { stat = "Average", label = "Disk / %" }]
          ]
        }
      },
      {
        type = "metric", x = 16, y = 8, width = 8, height = 6,
        properties = {
          title  = "EC2 status checks"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/EC2", "StatusCheckFailed", "InstanceId", aws_instance.app.id, { stat = "Maximum" }],
            ["AWS/EC2", "StatusCheckFailed_System", "InstanceId", aws_instance.app.id, { stat = "Maximum" }],
            ["AWS/EC2", "StatusCheckFailed_Instance", "InstanceId", aws_instance.app.id, { stat = "Maximum" }]
          ]
        }
      },
      {
        type = "log", x = 0, y = 14, width = 24, height = 8,
        properties = {
          title  = "Recent app logs"
          region = var.region
          query  = "SOURCE '${local.log_group_app}' | fields @timestamp, @message | sort @timestamp desc | limit 100"
          view   = "table"
        }
      }
    ]
  })
}
