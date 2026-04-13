resource "google_monitoring_dashboard" "cloud_run_dashboard" {
  dashboard_json = jsonencode({
    displayName = "Cloud Run APIs - SLO Overview (${terraform.workspace})"
    gridLayout = {
      columns = "2"
      widgets = [
        {
          title = "Global Request Rate per API"
          xyChart = {
            chartOptions = { mode = "COLOR" }
            dataSets = [
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\""
                    aggregation = {
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["resource.label.\"service_name\""]
                      alignmentPeriod    = "60s"
                    }
                  }
                }
                plotType = "LINE"
              }
            ]
          }
        },
        {
          title = "Global 5xx Errors Rate per API"
          xyChart = {
            chartOptions = { mode = "COLOR" }
            dataSets = [
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" metric.label.\"response_code_class\"=\"5xx\""
                    aggregation = {
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["resource.label.\"service_name\""]
                      alignmentPeriod    = "60s"
                    }
                  }
                }
                plotType = "LINE"
              }
            ]
          }
        },
        {
          title = "Latencies (p95) per API"
          xyChart = {
            chartOptions = { mode = "COLOR" }
            dataSets = [
              {
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\""
                    aggregation = {
                      perSeriesAligner   = "ALIGN_DELTA"
                      crossSeriesReducer = "REDUCE_PERCENTILE_95"
                      groupByFields      = ["resource.label.\"service_name\""]
                      alignmentPeriod    = "60s"
                    }
                  }
                }
                plotType = "LINE"
              }
            ]
          }
        }
      ]
    }
  })
}

resource "google_monitoring_dashboard" "functional_dashboard" {
  dashboard_json = jsonencode({
    displayName = "Zenika Console - Business Metrics (${terraform.workspace})"
    gridLayout = {
      columns = "2"
      widgets = [
        {
          title = "Agent Query Volume (Queries/min)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                prometheusQuery = "sum(rate(agent_queries_total[5m])) * 60"
              }
              plotType = "LINE"
            }]
          }
        },
        {
          title = "CV Processing Success Rate"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                prometheusQuery = "sum by (status) (increase(cv_processing_total[1h]))"
              }
              plotType = "STACKED_BAR"
            }]
          }
        },
        {
          title = "New User Accounts (Last 24h)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                prometheusQuery = "increase(user_creations_total[24h])"
              }
              plotType = "LINE"
            }]
          }
        },
        {
          title = "Login Success vs Failure"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                prometheusQuery = "sum by (status) (rate(user_logins_total[1h]))"
              }
              plotType = "LINE"
            }]
          }
        }
      ]
    }
  })
}
