from prometheus_client import Counter, Gauge

CV_PROCESSING_TOTAL = Counter("cv_processing_total", "Total number of CVs processed", ["status"])
CV_MISSING_EMBEDDINGS = Gauge("cv_missing_embeddings_total", "Number of CV profiles lacking a vector embedding")
