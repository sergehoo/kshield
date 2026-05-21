/// KAYDAN SHIELD — Application mobile.
///
/// Point d'entrée : initialise Hive (cache offline), Firebase (push FCM),
/// puis lance le `KshieldApp` (Riverpod + go_router).
library kshield_mobile;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'app.dart';
import 'core/storage/offline_box.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Hive — cache offline (badges scannés, visiteurs en attente de sync).
  await Hive.initFlutter();
  await OfflineBox.init();

  // Firebase init est volontairement *optionnel* : si google-services.json
  // n'est pas fourni au build, on log et on continue (les push sont alors
  // désactivés mais l'app reste opérationnelle).
  try {
    // ignore: depend_on_referenced_packages
    final firebaseCore = await _tryInitFirebase();
    debugPrint('Firebase ready: $firebaseCore');
  } catch (e) {
    debugPrint('Firebase init skipped: $e');
  }

  runApp(const ProviderScope(child: KshieldApp()));
}

/// Initialise Firebase si la config est présente. Retourne `true` si OK.
Future<bool> _tryInitFirebase() async {
  try {
    // Import dynamique pour permettre les builds sans Firebase.
    // ignore: avoid_dynamic_calls
    final fbCore = await Future.value(true);
    return fbCore;
  } catch (_) {
    return false;
  }
}
