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
    supplier = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

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
    class Ownership(models.TextChoices):
        INTERNAL = "INTERNAL", "Internal"
        CUSTOMER = "CUSTOMER", "Customer-owned"

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
    ownership = models.CharField(max_length=20, choices=Ownership.choices)

    # Internal placement
    terminal = models.ForeignKey(Terminal, on_delete=models.PROTECT, related_name="assets", null=True, blank=True)

    # Customer-owned placement
    customer_site = models.ForeignKey(
        CustomerSite, on_delete=models.PROTECT, related_name="assets", null=True, blank=True
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

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ownership="INTERNAL", terminal__isnull=False, customer_site__isnull=True)
                    | models.Q(ownership="CUSTOMER", customer_site__isnull=False, terminal__isnull=True)
                ),
                name="asset_ownership_location_consistency",
            )
        ]

    def __str__(self):
        return f"{self.tag} - {self.name}"

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
