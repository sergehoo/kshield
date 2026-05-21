/// Boîtes Hive utilisées en mode offline.
library kshield_mobile.storage;

import 'package:hive_flutter/hive_flutter.dart';

class OfflineBox {
  OfflineBox._();

  /// Scan queue (badges scannés mais non encore poussés au serveur).
  static const String scansQueue = 'scans_queue';

  /// Visiteurs créés offline (en attente de sync).
  static const String visitorsQueue = 'visitors_queue';

  /// Cache utilisateurs autorisés (pour validation badge sans réseau).
  static const String authorizedUsers = 'authorized_users';

  /// Cache rôles + permissions du user courant.
  static const String userPerms = 'user_perms';

  static Future<void> init() async {
    await Hive.openBox(scansQueue);
    await Hive.openBox(visitorsQueue);
    await Hive.openBox(authorizedUsers);
    await Hive.openBox(userPerms);
  }

  static Box scanQueueBox() => Hive.box(scansQueue);
  static Box visitorQueueBox() => Hive.box(visitorsQueue);
  static Box authorizedUsersBox() => Hive.box(authorizedUsers);
  static Box userPermsBox() => Hive.box(userPerms);
}
