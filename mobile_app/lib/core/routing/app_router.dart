/// Routage `go_router` avec redirection auth-aware.
library kshield_mobile.routing;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/dashboard/agent_dashboard_screen.dart';
import '../../features/home/home_screen.dart';
import '../../features/login/login_screen.dart';
import '../../features/scanner/nfc_scanner_screen.dart';
import '../../features/scanner/qr_scanner_screen.dart';
import '../../features/visitor/visitor_checkin_screen.dart';
import '../auth/auth_service.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authServiceProvider);

  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) async {
      final tokens = await auth.loadTokens();
      final loggedIn = tokens != null && !tokens.isExpired;
      final goingToLogin = state.matchedLocation == '/login';
      if (!loggedIn && !goingToLogin) return '/login';
      if (loggedIn && goingToLogin) return '/';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
      GoRoute(path: '/scan/qr', builder: (_, __) => const QrScannerScreen()),
      GoRoute(path: '/scan/nfc', builder: (_, __) => const NfcScannerScreen()),
      GoRoute(path: '/visitor', builder: (_, __) => const VisitorCheckinScreen()),
      GoRoute(path: '/agent', builder: (_, __) => const AgentDashboardScreen()),
    ],
  );
});
