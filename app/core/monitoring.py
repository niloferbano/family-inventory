from prometheus_client import Counter, Gauge, Histogram

WORKER_IN_FLIGHT = Gauge(
    "notification_worker_in_flight",
    "Number of messages currently being processed by the worker",
)
# Metric for throughput and failure tracking
WORKER_MESSAGE_TOTAL = Counter(
    "notification_worker_messages_total",
    "Total messages processed by the notification worker",
    ["status", "topic"],  # e.g., status="success", "retried", "dlq"
)

# Metric for latency tracking (Operational Excellence)
WORKER_PROCESS_LATENCY = Histogram(
    "notification_worker_process_duration_seconds",
    "Time spent processing a message",
    ["topic"],
)
WORKER_PROCESS_LATENCY = Histogram(
    "notification_worker_process_duration_seconds",
    "Time spent processing a message",
    ["topic"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

WORKER_MESSAGE_RETRIES_TOTAL = Counter(
    "notification_worker_retries_total",
    "Total retries performed by the notification worker",
    ["topic"],
)

WORKER_DB_ERRORS_TOTAL = Counter(
    "notification_worker_db_errors_total",
    "Database errors in notification worker",
    ["operation"],  # claim, finalize, ingest
)

WORKER_DLQ_TOTAL = Counter(
    "notification_worker_dlq_total",
    "Messages sent to DLQ",
    ["reason"],  # unprocessable, max_retries, schema_error
)
