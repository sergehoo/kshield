/// Client HTTP Dio configuré avec :
///   · BaseURL = `Env.apiBaseUrl`
///   · Interceptor d'auth (injection Bearer + refresh automatique sur 401)
///   · Logger (en debug uniquement)
///   · Timeouts configurables
///   · Fallback queue offline si pas de réseau
library kshield_mobile.network;

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:pretty_dio_logger/pretty_dio_logger.dart';

import '../auth/auth_service.dart';
import '../config/env.dart';
import '../storage/offline_box.dart';

class ApiClient {
  final Dio _dio;
  final AuthService _auth;

  ApiClient(this._auth)
      : _dio = Dio(BaseOptions(
          baseUrl: Env.apiBaseUrl,
          connectTimeout: const Duration(seconds: Env.httpTimeoutSec),
          receiveTimeout: const Duration(seconds: Env.httpTimeoutSec),
          headers: const {
            'Accept': 'application/json',
            'X-Client': 'kshield-mobile',
          },
        )) {
    _dio.interceptors.add(_AuthInterceptor(_auth));
    if (Env.debugLogging) {
      _dio.interceptors.add(PrettyDioLogger(
        requestHeader: false,
        requestBody: true,
        responseBody: false,
        compact: true,
      ));
    }
  }

  Dio get dio => _dio;

  /// Vérifie la connectivité réseau.
  Future<bool> isOnline() async {
    final r = await Connectivity().checkConnectivity();
    return !r.contains(ConnectivityResult.none);
  }

  /// Pousse un scan badge offline-safe : essai online puis queue Hive.
  Future<void> queueOrSendScan(Map<String, dynamic> payload) async {
    if (await isOnline()) {
      try {
        await _dio.post('/api/v1/access/scans/', data: payload);
        return;
      } catch (_) {
        // Tombe sur la queue offline
      }
    }
    OfflineBox.scanQueueBox().add(payload);
  }

  /// Vide la queue offline (à appeler dès que la connectivité revient).
  Future<int> flushQueue() async {
    if (!await isOnline()) return 0;
    final box = OfflineBox.scanQueueBox();
    var sent = 0;
    final keys = box.keys.toList();
    for (final k in keys) {
      final payload = Map<String, dynamic>.from(box.get(k) as Map);
      try {
        await _dio.post('/api/v1/mobile/sync/push/', data: {
          'scans': [payload]
        });
        await box.delete(k);
        sent++;
      } catch (_) {
        break; // arrête au premier échec — on retentera plus tard
      }
    }
    return sent;
  }
}

class _AuthInterceptor extends Interceptor {
  final AuthService _auth;
  _AuthInterceptor(this._auth);

  @override
  Future<void> onRequest(
      RequestOptions options, RequestInterceptorHandler handler) async {
    final tokens = await _auth.refreshIfNeeded() ?? await _auth.loadTokens();
    if (tokens != null) {
      options.headers['Authorization'] = 'Bearer ${tokens.accessToken}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
      DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401) {
      // Refresh tenté ; si échec, on logout et propage
      final fresh = await _auth.refreshIfNeeded();
      if (fresh == null) {
        await _auth.logout();
      }
    }
    handler.next(err);
  }
}

final apiClientProvider = Provider<ApiClient>((ref) {
  final auth = ref.watch(authServiceProvider);
  return ApiClient(auth);
});
