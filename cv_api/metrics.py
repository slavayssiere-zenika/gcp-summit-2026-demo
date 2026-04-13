from prometheus_client import Counter

CV_PROCESSING_TOTAL = Counter("cv_processing_total", "Total number of CVs processed", ["status"])
