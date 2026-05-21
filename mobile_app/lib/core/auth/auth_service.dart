/// Service d'authentification OIDC Keycloak (PKCE) + refresh token.
///
/// Utilise `flutter_appauth` côté natif (Android Custom Tabs / iOS ASWebAuth).
/// Le redirect URI est `com.kaydan.shield://oauth/redirect` (à configurer dans
/// AndroidManifest.xml et Info.plist).
library kshield_mobile.auth;

import 'package:flutter_appauth/flutter_appauth.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:jwt_decoder/jwt_decoder.dart';

import '../config/env.dart';

class AuthTokens {
  final String accessToken;
  final String? refreshToken;
  final DateTime expiresAt;
  final String? idToken;

  AuthTokens({
    required this.accessToken,
    required this.expiresAt,
    this.refreshToken,
    this.idToken,
  });

  bool get isExpired =>
      DateTime.now().isAfter(expiresAt.subtract(const Duration(seconds: 30)));

  Map<String, dynamic> get claims => JwtDecoder.decode(accessToken);

  Map<String, dynamic> toJson() => {
        'access_token': accessToken,
        'refresh_token': refreshToken,
        'expires_at': expiresAt.toIso8601String(),
        'id_token': idToken,
      };

  static AuthTokens fromJson(Map<String, dynamic> j) => AuthTokens(
        accessToken: j['access_token'] as String,
        refreshToken: j['refresh_token'] as String?,
        expiresAt: DateTime.parse(j['expires_at'] as String),
        idToken: j['id_token'] as String?,
      );
}

class AuthService {
  final FlutterAppAuth _appAuth;
  final FlutterSecureStorage _storage;

  AuthService({
    FlutterAppAuth? appAuth,
    FlutterSecureStorage? storage,
  })  : _appAuth = appAuth ?? const FlutterAppAuth(),
        _storage = storage ?? const FlutterSecureStorage();

  static const _kTokensKey = 'auth_tokens';

  /// Lance le flow OIDC Authorization Code + PKCE.
  Future<AuthTokens> login() async {
    final result = await _appAuth.authorizeAndExchangeCode(
      AuthorizationTokenRequest(
        Env.ssoClientId,
        Env.ssoRedirectUri,
        issuer: Env.ssoIssuer,
        scopes: Env.ssoScopes,
        preferEphemeralSession: false,
        promptValues: const ['login'],
      ),
    );

    final tokens = AuthTokens(
      accessToken: result.accessToken!,
      refreshToken: result.refreshToken,
      idToken: result.idToken,
      expiresAt: result.accessTokenExpirationDateTime ??
          DateTime.now().add(const Duration(minutes: 30)),
    );
    await _persist(tokens);
    return tokens;
  }

  /// Rafraîchit les tokens si nécessaire. Retourne null si refresh impossible.
  Future<AuthTokens?> refreshIfNeeded() async {
    final current = await loadTokens();
    if (current == null) return null;
    if (!current.isExpired) return current;
    if (current.refreshToken == null) return null;

    try {
      final result = await _appAuth.token(TokenRequest(
        Env.ssoClientId,
        Env.ssoRedirectUri,
        issuer: Env.ssoIssuer,
        refreshToken: current.refreshToken,
        grantType: 'refresh_token',
        scopes: Env.ssoScopes,
      ));
      final tokens = AuthTokens(
        accessToken: result.accessToken!,
        refreshToken: result.refreshToken ?? current.refreshToken,
        idToken: result.idToken ?? current.idToken,
        expiresAt: result.accessTokenExpirationDateTime ??
            DateTime.now().add(const Duration(minutes: 30)),
      );
      await _persist(tokens);
      return tokens;
    } catch (_) {
      await logout();
      return null;
    }
  }

  Future<AuthTokens?> loadTokens() async {
    final raw = await _storage.read(key: _kTokensKey);
    if (raw == null) return null;
    try {
      final json = Map<String, dynamic>.from(
        // ignore: avoid_dynamic_calls
        Uri.splitQueryString(raw).isEmpty
            ? const {}
            : Uri.splitQueryString(raw),
      );
      // Fallback : raw est un JSON sérialisé
      if (json.isEmpty) {
        return AuthTokens.fromJson(_simpleJsonParse(raw));
      }
      return AuthTokens.fromJson(json);
    } catch (_) {
      return null;
    }
  }

  Future<void> logout() async {
    await _storage.delete(key: _kTokensKey);
  }

  Future<void> _persist(AuthTokens t) async {
    await _storage.write(key: _kTokensKey, value: _simpleJsonEncode(t.toJson()));
  }

  // ─── JSON helpers — pas de dépendance sur `dart:convert` au top-level
  //     pour rester lisible ; ils restent volontairement simples. ───────
  String _simpleJsonEncode(Map<String, dynamic> m) {
    final entries = m.entries
        .where((e) => e.value != null)
        .map((e) => '"${e.key}":${_encodeValue(e.value)}')
        .join(',');
    return '{$entries}';
  }

  String _encodeValue(Object? v) {
    if (v == null) return 'null';
    if (v is num || v is bool) return '$v';
    return '"${v.toString().replaceAll('"', r'\"')}"';
  }

  Map<String, dynamic> _simpleJsonParse(String raw) {
    // Très simple parser — convient pour notre format contrôlé
    final body = raw.replaceAll(RegExp(r'^\{|\}$'), '');
    final result = <String, dynamic>{};
    for (final part in _splitTopLevel(body, ',')) {
      final idx = part.indexOf(':');
      if (idx < 0) continue;
      final key = part.substring(0, idx).trim().replaceAll('"', '');
      final value = part.substring(idx + 1).trim();
      if (value == 'null') {
        result[key] = null;
      } else if (value.startsWith('"')) {
        result[key] = value.substring(1, value.length - 1);
      } else {
        result[key] = num.tryParse(value) ?? value;
      }
    }
    return result;
  }

  Iterable<String> _splitTopLevel(String s, String sep) sync* {
    var depth = 0;
    var inString = false;
    final buf = StringBuffer();
    for (var i = 0; i < s.length; i++) {
      final ch = s[i];
      if (ch == '"' && (i == 0 || s[i - 1] != '\\')) inString = !inString;
      if (!inString) {
        if (ch == '{' || ch == '[') depth++;
        if (ch == '}' || ch == ']') depth--;
        if (ch == sep && depth == 0) {
          yield buf.toString();
          buf.clear();
          continue;
        }
      }
      buf.write(ch);
    }
    if (buf.isNotEmpty) yield buf.toString();
  }
}

final authServiceProvider = Provider<AuthService>((ref) => AuthService());

/// Provider qui expose les tokens courants (null si déconnecté).
final authTokensProvider = FutureProvider<AuthTokens?>((ref) async {
  final svc = ref.watch(authServiceProvider);
  return svc.refreshIfNeeded() ?? svc.loadTokens();
});
