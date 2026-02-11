class UnprocessableMessageError(Exception):
    """
    Raised when a message is permanently invalid and must not be retried.
    Examples:
    - Invalid JSON
    - Missing required routing metadata
    - Missing event_id/home_id
    """

    pass
