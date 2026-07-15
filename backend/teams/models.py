from django.conf import settings
from django.db import models

from assets.models import ImmutableModel, Site


class Team(models.Model):
    """A crew based at one site. Site-scoped like everything else
    (assets.access) - a team belongs to exactly one site."""

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="teams")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="teams")
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="led_teams"
    )

    class Meta:
        unique_together = ("site", "code")

    def __str__(self):
        return f"{self.site.code}/{self.code} ({self.name})"


class Shift(models.Model):
    """A recurring time pattern a team works, e.g. "Day" 06:00-14:00 on
    weekdays. Not calendar-exact scheduling - just enough to say which
    team/shift a ticket or PM schedule belongs to."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="shifts")
    name = models.CharField(max_length=100, help_text='e.g. "Day", "Night", "Weekend"')
    start_time = models.TimeField()
    end_time = models.TimeField()
    days_of_week = models.CharField(
        max_length=50,
        default="Mon,Tue,Wed,Thu,Fri",
        help_text="Comma-separated: Mon,Tue,Wed,Thu,Fri,Sat,Sun",
    )

    def __str__(self):
        return f"{self.team} - {self.name} ({self.start_time}-{self.end_time})"


class ShiftHandoverNote(ImmutableModel):
    """Append-only continuity notes between shifts - not something anyone
    should be able to quietly edit after the fact."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="handover_notes")
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="handover_notes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.team} handover ({self.created_at:%Y-%m-%d %H:%M})"
