/// Configuration runtime (à override via `--dart-define`).
///
/// Exemple build :
///   flutter build apk --dart-define=API_BASE_URL=https://api.kaydangroupe.com \
///                     --dart-define=SSO_ISSUER=https://sso.kaydangroupe.com/realms/kaydan \
///                     --dart-define=SSO_CLIENT_ID=kshield-mobile \
///                     --dart-define=SSO_REDIRECT=com.kaydan.shield://oauth/redirect
library kshield_mobile.env;

class Env {
  Env._();

  /// URL racine de l'API REST (KAYDAN SHIELD backend Django).
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://api.kaydangroupe.com',
  );

  /// Issuer OIDC Keycloak.
  static const String ssoIssuer = String.fromEnvironment(
    'SSO_ISSUER',
    defaultValue: 'https://sso.kaydangroupe.com/realms/kaydan',
  );

  /// Client ID OIDC (Public Client + PKCE).
  static const String ssoClientId = String.fromEnvironment(
    'SSO_CLIENT_ID',
    defaultValue: 'kshield-mobile',
  );

  /// Redirect URI (doit matcher la config Keycloak ET le deeplink natif).
  static const String ssoRedirectUri = String.fromEnvironment(
    'SSO_REDIRECT',
    defaultValue: 'com.kaydan.shield://oauth/redirect',
  );

  /// Scopes OIDC demandés. `offline_access` permet le refresh-token.
  static const List<String> ssoScopes = [
    'openid', 'profile', 'email', 'offline_access',
  ];

  /// Timeout HTTP global (secondes).
  static const int httpTimeoutSec = 12;

  /// Activer les logs verbeux (à False en release).
  static const bool debugLogging = bool.fromEnvironment(
    'DEBUG_LOGGING',
    defaultValue: false,
  );
}
