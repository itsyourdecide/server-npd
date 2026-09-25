import re
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext as _


class Notification(models.Model):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-app"

    class Event(models.TextChoices):
        REQUEST_STATE_CHANGED = "request.state_changed", "Request state changed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    channel = models.CharField(
        max_length=16,
        choices=Channel,
        default=Channel.IN_APP,
    )
    event = models.CharField(max_length=64, choices=Event)
    title = models.CharField(max_length=200)
    message = models.TextField()
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=128)
    deduplication_key = models.CharField(max_length=200, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["recipient", "read_at", "created_at"],
                name="notifications_recipient_idx",
            ),
        ]

    @property
    def localized_title(self):
        prefix = "Request status: "
        if self.event == self.Event.REQUEST_STATE_CHANGED and self.title.startswith(
            prefix
        ):
            state = _(self.title.removeprefix(prefix))
            return _("Request status: %(state)s") % {"state": state}
        return self.title

    @property
    def localized_message(self):
        if self.event == self.Event.REQUEST_STATE_CHANGED:
            match = re.fullmatch(r'Your request "(.*)" changed to (.*)\.', self.message)
            if match:
                title, state = match.groups()
                return _(
                    'Your request "%(title)s" changed to %(state)s.'
                ) % {"title": title, "state": _(state)}
        return self.message

    def __str__(self) -> str:
        return self.title
