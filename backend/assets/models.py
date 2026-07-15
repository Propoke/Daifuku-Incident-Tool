from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models


class ImmutableModel(models.Model):
    """Base for append-only records: once created, rows are never edited or deleted.

    Used for ConfigurationVersion and AssetConfigurationAssignment per the
    architecture risk audit (docs/cmms-feature-draft.md) - history queries
    like "what was this asset running on March 3rd" need to be a first-class
    query against real rows, not a fragile join against a mutable-plus-log
    table.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError(f"{self.__class__.__name__} rows are immutable; create a new one instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(f"{self.__class__.__name__} rows are immutable and cannot be deleted.")


# --- Locations: internal (Site/Terminal) vs. customer (Customer/CustomerSite) ---


class Site(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)

    # Who can see this site's tickets/stock/assets - see assets/access.py.
    # A user's effective access is the union of their own assignment here
    # plus every group they belong to's assignment. Users in the "Admin" or
    # "OEM" group, and superusers, bypass this entirely (see everything) -
    # not represented here, handled in assets/access.py.
    allowed_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="accessible_sites")
    allowed_groups = models.ManyToManyField(Group, blank=True, related_name="accessible_sites")

    def __str__(self):
        return self.name


class Terminal(models.Model):
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="terminals")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)

    class Meta:
        unique_together = ("site", "code")

    def __str__(self):
        return f"{self.site.code}/{self.code}"


class Customer(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class CustomerContact(models.Model):
    """Marks a User as a customer portal account (see the portal app) -
    presence of this record is what portal views check, not is_staff
    (which stays False for these accounts, so they can never reach
    /admin/ even by guessing the URL). Local username/password auth
    (Django's ModelBackend, already an active AUTHENTICATION_BACKENDS
    entry) - separate from the Entra OIDC flow used by internal staff."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_contact")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="contacts")
    phone = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.user.get_username()} ({self.customer.name})"


class CustomerSite(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sites")
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f"{self.customer.name} / {self.name}"


class ServiceContract(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="contracts")
    name = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    sla_description = models.TextField(blank=True)
    # Machine-checkable targets, in addition to the free-text description
    # above - what workorders.sla.get_sla_status() actually measures
    # against. Either or both may be left blank if this contract has no
    # hard SLA commitment.
    sla_response_hours = models.PositiveIntegerField(
        null=True, blank=True, help_text="Target hours from ticket creation to work starting"
    )
    sla_resolution_hours = models.PositiveIntegerField(
        null=True, blank=True, help_text="Target hours from ticket creation to close"
    )

    def __str__(self):
        return f"{self.customer.name} - {self.name}"


# --- Items & spare parts ---


class Item(models.Model):
    """A logical component/module (e.g. "Drive Motor") that a Configuration is
    built from. Always orderable in principle, independent of whether any
    SparePart currently fulfilling it is in stock anywhere."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Vendor(models.Model):
    """A real supplier record - name, contact, lead time - instead of the
    free-text SparePart.supplier field that preceded it. Foundation for
    the purchase-order workflow (inventory.PurchaseOrder): a PO needs
    somewhere to actually order from, with a lead time to estimate an ETA
    against."""

    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    lead_time_days = models.PositiveIntegerField(null=True, blank=True, help_text="Typical order-to-delivery time")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class SparePart(models.Model):
    """The stocked, orderable SKU that fulfills one or more Items. Stock level
    is a property of this record, not of the Item it fulfills."""

    sku = models.CharField(max_length=100, unique=True)
    # Separate from sku: the printed/scanned symbology value, which may
    # differ from the human-readable SKU. Nullable since not every part has
    # a physical barcode label yet; scanning lookups fall back to sku.
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description = models.CharField(max_length=300, blank=True)
    items = models.ManyToManyField(Item, related_name="spare_parts")
    # Free-text, kept for parts that haven't been assigned a real Vendor
    # record yet - vendor below is the structured replacement (contact
    # info, lead time) new purchasing should use.
    supplier = models.CharField(max_length=200, blank=True)
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="spare_parts"
    )
    is_active = models.BooleanField(default=True)
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Used for parts cost reporting"
    )

    def __str__(self):
        return self.sku


# --- Configuration: template -> immutable versions -> per-asset assignment ---


class ConfigurationTemplate(models.Model):
    """A named "how a machine type is built" template. Editable itself - the
    individual versions under it are not (see ConfigurationVersion)."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ConfigurationVersion(ImmutableModel):
    """One immutable, dated bill-of-Items. `template` is null for a one-off
    version created to override a single asset's configuration without
    mutating the shared template (see AssetConfigurationAssignment)."""

    template = models.ForeignKey(
        ConfigurationTemplate,
        on_delete=models.PROTECT,
        related_name="versions",
        null=True,
        blank=True,
    )
    version_label = models.CharField(max_length=50, help_text='e.g. "v3" or a date-based label')
    effective_date = models.DateField(help_text="Since when this version applies, shown to users at a glance")
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    items = models.ManyToManyField(Item, through="ConfigurationVersionItem")

    def __str__(self):
        label = self.template.name if self.template else "(asset-specific override)"
        return f"{label} {self.version_label}"


class ConfigurationVersionItem(models.Model):
    # Not immutable like its parent ConfigurationVersion - rows are meant to
    # be created once alongside the version and left alone, but that's not
    # enforced at the DB/model layer yet. Tighten if this becomes a problem
    # in practice (e.g. restrict edits once the version has any
    # AssetConfigurationAssignment referencing it).
    configuration_version = models.ForeignKey(ConfigurationVersion, on_delete=models.PROTECT)
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("configuration_version", "item")


# --- Assets ---


class Asset(models.Model):
    class Status(models.TextChoices):
        INSTALLED = "INSTALLED", "Installed"
        ACTIVE = "ACTIVE", "Active"
        IN_MAINTENANCE = "IN_MAINTENANCE", "In maintenance"
        DECOMMISSIONED = "DECOMMISSIONED", "Decommissioned"

    class Criticality(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    tag = models.CharField(max_length=100, unique=True, help_text="Asset tag / QR-code identifier")
    name = models.CharField(max_length=200)

    # Physical location, required for every asset regardless of who owns
    # it - this is what site-scoping (assets.access) keys off. Visibility
    # is determined by site access alone, not by ownership.
    terminal = models.ForeignKey(Terminal, on_delete=models.PROTECT, related_name="assets")

    # Ownership is an identifying/billing attribute, not an access-control
    # one: null means internally owned; set means owned by that customer,
    # even though the asset still physically sits at (and is scoped by)
    # one of our own Sites/Terminals. customer_site/service_contract are
    # optional context for that ownership (billing address, SLA contract),
    # independent of the physical terminal above.
    owner_customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="owned_assets", null=True, blank=True
    )
    customer_site = models.ForeignKey(
        CustomerSite, on_delete=models.SET_NULL, related_name="assets", null=True, blank=True
    )
    service_contract = models.ForeignKey(
        ServiceContract, on_delete=models.SET_NULL, related_name="assets", null=True, blank=True
    )

    manufacturer = models.CharField(max_length=200, blank=True)
    model = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=200, blank=True)
    install_date = models.DateField(null=True, blank=True)
    firmware_version = models.CharField(max_length=100, blank=True)
    software_version = models.CharField(max_length=100, blank=True)
    criticality = models.CharField(max_length=10, choices=Criticality.choices, default=Criticality.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INSTALLED)

    def __str__(self):
        return f"{self.tag} - {self.name}"

    @property
    def is_customer_owned(self):
        return self.owner_customer_id is not None

    @property
    def current_configuration_assignment(self):
        return self.configuration_assignments.order_by("-effective_date", "-created_at").first()


class AssetConfigurationAssignment(ImmutableModel):
    """Append-only: an asset's current configuration is the latest row here
    by effective_date, not a mutable field on Asset. Reassigning a
    configuration means adding a new row, never editing the old one - this
    is what makes "what was this asset running on March 3rd" a plain query."""

    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="configuration_assignments")
    configuration_version = models.ForeignKey(
        ConfigurationVersion, on_delete=models.PROTECT, related_name="asset_assignments"
    )
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.asset.tag} -> {self.configuration_version} (since {self.effective_date})"


class AssetMeterReading(ImmutableModel):
    """A cumulative, odometer-style reading (running hours or cycle count),
    manually logged - v1 input method per the CMMS audit; an IoT/sensor
    feed would write to this same model later without changing anything
    downstream. Append-only like other logs here: correcting a bad
    reading means logging a new one, not editing history, since
    maintenance.PMSchedule's meter-based trigger depends on this being a
    reliable historical record, not a mutable "current value" field."""

    class MeterType(models.TextChoices):
        HOURS = "HOURS", "Running hours"
        CYCLES = "CYCLES", "Cycles"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="meter_readings")
    meter_type = models.CharField(max_length=20, choices=MeterType.choices)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    recorded_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.asset.tag} {self.get_meter_type_display()}: {self.value} @ {self.recorded_at:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        if self.recorded_at is None:
            from django.utils import timezone

            self.recorded_at = timezone.now()
        super().save(*args, **kwargs)

    @classmethod
    def latest_value(cls, asset, meter_type):
        reading = cls.objects.filter(asset=asset, meter_type=meter_type).order_by("-recorded_at").first()
        return reading.value if reading else None
