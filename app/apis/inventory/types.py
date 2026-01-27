from enum import StrEnum


class InventoryCategory(StrEnum):
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    CLEANING = "cleaning"
    OTHER = "other"


class InventoryAlertType(StrEnum):
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"
