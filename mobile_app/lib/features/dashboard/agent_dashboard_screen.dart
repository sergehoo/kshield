/// Tableau de bord agent — KPIs temps réel (scans/min, alertes ouvertes).
library kshield_mobile.features.dashboard;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';

class AgentDashboardScreen extends ConsumerStatefulWidget {
  const AgentDashboardScreen({super.key});

  @override
  ConsumerState<AgentDashboardScreen> createState() =>
      _AgentDashboardScreenState();
}

class _AgentDashboardScreenState
    extends ConsumerState<AgentDashboardScreen> {
  Timer? _timer;
  Map<String, dynamic>? _stats;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final api = ref.read(apiClientProvider);
      final r = await api.dio.get('/api/v1/reports/dashboards/agent_summary/');
      setState(() {
        _stats = Map<String, dynamic>.from(r.data as Map);
        _error = null;
      });
    } catch (e) {
      setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Supervision agent'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null)
              Card(
                color: Colors.red.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text('Erreur : $_error',
                      style: TextStyle(color: Colors.red.shade900)),
                ),
              ),
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 1.4,
              children: [
                _KpiCard(
                  label: 'Scans / dernière h',
                  value: '${_stats?['scans_hour'] ?? '—'}',
                  icon: Icons.bolt,
                  color: Colors.blue,
                ),
                _KpiCard(
                  label: 'Alertes ouvertes',
                  value: '${_stats?['alerts_open'] ?? '—'}',
                  icon: Icons.shield,
                  color: Colors.red,
                ),
                _KpiCard(
                  label: 'Visiteurs sur site',
                  value: '${_stats?['visitors_on_site'] ?? '—'}',
                  icon: Icons.people,
                  color: Colors.teal,
                ),
                _KpiCard(
                  label: 'Casques actifs',
                  value: '${_stats?['helmets_active'] ?? '—'}',
                  icon: Icons.engineering,
                  color: Colors.amber.shade800,
                ),
              ],
            ),
            const SizedBox(height: 18),
            const Text('Dernières alertes',
                style: TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            ..._buildAlerts(),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildAlerts() {
    final alerts = (_stats?['recent_alerts'] as List?) ?? const [];
    if (alerts.isEmpty) {
      return [
        const Card(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Text('Aucune alerte récente.'),
          ),
        )
      ];
    }
    return alerts.map((a) {
      final m = Map<String, dynamic>.from(a as Map);
      return Card(
        child: ListTile(
          leading: CircleAvatar(
            backgroundColor: _sevColor(m['severity']?.toString()),
            child: const Icon(Icons.warning, color: Colors.white, size: 18),
          ),
          title: Text(m['rule']?.toString() ?? '—'),
          subtitle: Text(
              '${m['site'] ?? '—'} · ${(m['ts'] ?? '').toString().substring(0, 16)}'),
          trailing: Text(m['severity']?.toString() ?? '',
              style: const TextStyle(fontWeight: FontWeight.w600)),
        ),
      );
    }).toList();
  }

  Color _sevColor(String? s) {
    switch (s) {
      case 'critical':
        return Colors.red.shade700;
      case 'high':
        return Colors.deepOrange;
      case 'medium':
        return Colors.amber.shade700;
      default:
        return Colors.blueGrey;
    }
  }
}

class _KpiCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;

  const _KpiCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(icon, color: color, size: 22),
            Text(value,
                style: const TextStyle(
                    fontSize: 24, fontWeight: FontWeight.w700)),
            Text(label,
                style: TextStyle(
                    fontSize: 12, color: Colors.grey.shade600)),
          ],
        ),
      ),
    );
  }
}
