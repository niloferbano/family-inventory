from enum import StrEnum


class InventoryAlertType(StrEnum):
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"
