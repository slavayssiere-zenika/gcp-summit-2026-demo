from prometheus_client import Counter, Gauge, Histogram

CV_PROCESSING_TOTAL = Counter("cv_processing_total", "Total number of CVs processed", ["status"])
CV_MISSING_EMBEDDINGS = Gauge("cv_missing_embeddings_total", "Number of CV profiles lacking a vector embedding")

# R6 — Métrique du filtre de pertinence (R2 : VECTOR_DISTANCE_THRESHOLD)
# Permet de monitorer en production la proportion de candidats élagués par le seuil.
CV_SEARCH_THRESHOLD_FILTERED = Counter(
    "cv_search_threshold_filtered_total",
    "Number of CV candidates excluded by the vector distance threshold (R2 filter)",
    ["agency"],
)

# R6 — Distribution des scores de similarité retournés (pour calibrer le seuil)
CV_SEARCH_RESULT_SCORE = Histogram(
    "cv_search_result_similarity_score",
    "Similarity score distribution of candidates returned by search",
    buckets=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
