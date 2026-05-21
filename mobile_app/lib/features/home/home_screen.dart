/// Écran d'accueil — tuiles d'action pour vigile, visiteur, agent.
library kshield_mobile.features.home;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/auth/auth_service.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('KAYDAN SHIELD'),
        actions: [
          IconButton(
            tooltip: 'Déconnexion',
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await ref.read(authServiceProvider).logout();
              if (context.mounted) context.go('/login');
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: GridView.count(
            crossAxisCount: 2,
            crossAxisSpacing: 14,
            mainAxisSpacing: 14,
            children: [
              _Tile(
                title: 'Scanner badge QR',
                subtitle: 'Vigile · accès rapide',
                icon: Icons.qr_code_scanner,
                color: Colors.blue,
                onTap: () => context.push('/scan/qr'),
              ),
              _Tile(
                title: 'Scanner NFC',
                subtitle: 'Badge sans contact',
                icon: Icons.nfc,
                color: Colors.deepPurple,
                onTap: () => context.push('/scan/nfc'),
              ),
              _Tile(
                title: 'Check-in visiteur',
                subtitle: 'Self-service accueil',
                icon: Icons.person_add_alt,
                color: Colors.teal,
                onTap: () => context.push('/visitor'),
              ),
              _Tile(
                title: 'Supervision',
                subtitle: 'Tableau de bord agent',
                icon: Icons.dashboard,
                color: Colors.orange,
                onTap: () => context.push('/agent'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _Tile({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: color, size: 26),
              ),
              const Spacer(),
              Text(title,
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              Text(subtitle,
                  style: TextStyle(
                      fontSize: 12, color: Colors.grey.shade600)),
            ],
          ),
        ),
      ),
    );
  }
}
