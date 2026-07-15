from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class CMMSOIDCBackend(OIDCAuthenticationBackend):
    """Authenticates internal users against Entra ID.

    Entra security-group -> CMMS role mapping isn't wired up yet: that
    needs the real group object IDs from the app registration, which don't
    exist until Entra is configured for this app. Extend _sync_profile()
    to read the `groups` claim once those IDs are known.
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
        user.save()
