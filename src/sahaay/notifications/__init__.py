"""
Sahaay AI - Notifications Subsystem
Manages user corridor subscriptions, risk alerts, deduplication cooldowns, and audit logs.
"""

from sahaay.notifications.schemas import (
    NotificationSeverity,
    NotificationType,
    NotificationDeliveryChannel,
    NotificationRecord,
    SubscriptionRequest,
    SubscriptionRecord,
)
from sahaay.notifications.service import (
    NotificationService,
    default_notification_service,
)

__all__ = [
    "NotificationSeverity",
    "NotificationType",
    "NotificationDeliveryChannel",
    "NotificationRecord",
    "SubscriptionRequest",
    "SubscriptionRecord",
    "NotificationService",
    "default_notification_service",
]
