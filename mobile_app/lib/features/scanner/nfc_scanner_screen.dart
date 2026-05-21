/// Scanner NFC — lit l'UID d'un badge MIFARE/HCE et l'envoie à l'API.
library kshield_mobile.features.scanner.nfc;

import 'package:flutter/material.dart';
import 'package:flutter_nfc_kit/flutter_nfc_kit.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';

class NfcScannerScreen extends ConsumerStatefulWidget {
  const NfcScannerScreen({super.key});

  @override
  ConsumerState<NfcScannerScreen> createState() => _NfcScannerScreenState();
}

class _NfcScannerScreenState extends ConsumerState<NfcScannerScreen> {
  String _status = 'Approchez un badge NFC';
  bool _busy = false;

  Future<void> _scan() async {
    setState(() {
      _busy = true;
      _status = 'En attente d\'un badge…';
    });
    try {
      final availability = await FlutterNfcKit.nfcAvailability;
      if (availability != NFCAvailability.available) {
        setState(() => _status = 'NFC indisponible sur cet appareil.');
        return;
      }
      final tag = await FlutterNfcKit.poll(
        timeout: const Duration(seconds: 15),
        iosMultipleTagMessage: 'Plusieurs badges détectés',
        iosAlertMessage: 'Tenez le badge près de l\'appareil',
      );
      final uid = tag.id;
      setState(() => _status = 'Badge lu : $uid');

      await ref.read(apiClientProvider).queueOrSendScan({
        'badge_uid': uid,
        'method': 'nfc',
        'source': 'mobile',
        'tag_type': tag.type.name,
        'client_ts': DateTime.now().toUtc().toIso8601String(),
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: Colors.green.shade700,
          content: Text('Scan envoyé : $uid'),
        ));
      }
    } catch (e) {
      setState(() => _status = 'Erreur : $e');
    } finally {
      await FlutterNfcKit.finish();
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scanner NFC')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.nfc, size: 96, color: Colors.deepPurple.shade300),
              const SizedBox(height: 24),
              Text(_status, textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 15)),
              const SizedBox(height: 32),
              FilledButton.icon(
                onPressed: _busy ? null : _scan,
                icon: const Icon(Icons.contactless),
                label: Text(_busy ? 'Scan en cours…' : 'Démarrer scan NFC'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
