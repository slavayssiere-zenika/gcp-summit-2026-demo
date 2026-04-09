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
