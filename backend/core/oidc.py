from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class CMMSOIDCBackend(OIDCAuthenticationBackend):
    """Authenticates internal users against Entra ID.

    Entra security-group -> CMMS role mapping isn't wired up yet: that
    needs the real group object IDs from the app registration, which don't
    exist until Entra is configured for this app. Extend _sync_profile()
    to add the user to the matching Django Group ("Admin", "Incident
    Manager", "Management", "Technician", "Lead Technician", "Spare Parts
    Manager" - see core/migrations/0001_create_roles.py) once those IDs
    are known. Until then, role assignment is manual: an existing admin
    adds the user to a group via /admin/auth/user/.
    """

    def get_username(self, claims):
        return claims.get("email") or claims.get("preferred_username") or claims["sub"]

    def create_user(self, claims):
        user = super().create_user(claims)
        self._sync_profile(user, claims)
        return user

    def update_user(self, user, claims):
        self._sync_profile(user, claims)
        return user

    def _sync_profile(self, user, claims):
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.email = claims.get("email", "")
        # Django admin is the only UI right now (see infra plan), so every
        # authenticated internal user needs is_staff to reach it at all -
        # the RBAC groups then gate what they actually see/can do inside.
        # Revisit once a dedicated frontend exists: is_staff should then be
        # reserved for users who genuinely need the admin panel.
        user.is_staff = True
        user.save()
