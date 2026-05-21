/// Workflow de check-in visiteur self-service.
///
/// Saisie identité → photo → soumission → réception du QR temporaire.
library kshield_mobile.features.visitor;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/network/api_client.dart';

class VisitorCheckinScreen extends ConsumerStatefulWidget {
  const VisitorCheckinScreen({super.key});

  @override
  ConsumerState<VisitorCheckinScreen> createState() =>
      _VisitorCheckinScreenState();
}

class _VisitorCheckinScreenState extends ConsumerState<VisitorCheckinScreen> {
  final _firstName = TextEditingController();
  final _lastName = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _company = TextEditingController();
  final _hostMatricule = TextEditingController();
  final _reason = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  XFile? _photo;
  bool _submitting = false;
  String? _resultBadgeUid;

  Future<void> _takePhoto() async {
    final picker = ImagePicker();
    final file = await picker.pickImage(
      source: ImageSource.camera,
      preferredCameraDevice: CameraDevice.front,
      maxWidth: 800,
      imageQuality: 78,
    );
    if (file != null) setState(() => _photo = file);
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _submitting = true);
    try {
      final payload = {
        'first_name': _firstName.text.trim(),
        'last_name': _lastName.text.trim(),
        'phone': _phone.text.trim(),
        'email': _email.text.trim(),
        'company': _company.text.trim(),
        'host_matricule': _hostMatricule.text.trim(),
        'reason': _reason.text.trim(),
        'source': 'mobile',
      };
      final api = ref.read(apiClientProvider);
      final resp = await api.dio.post('/api/v1/visitors/self-checkin/',
          data: payload);
      final badge = resp.data['badge_uid'] as String?;
      setState(() => _resultBadgeUid = badge);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: Colors.green.shade700,
          content: Text('Check-in OK — badge $badge'),
        ));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: Colors.red.shade700,
          content: Text('Échec : $e'),
        ));
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Check-in visiteur')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_resultBadgeUid != null)
                  Card(
                    color: Colors.green.shade50,
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        children: [
                          Icon(Icons.check_circle,
                              size: 48, color: Colors.green.shade700),
                          const SizedBox(height: 8),
                          const Text('Visite enregistrée'),
                          Text('Badge : $_resultBadgeUid',
                              style: const TextStyle(
                                  fontFamily: 'monospace',
                                  fontWeight: FontWeight.bold)),
                        ],
                      ),
                    ),
                  ),
                _field('Prénom', _firstName, required: true),
                _field('Nom', _lastName, required: true),
                _field('Téléphone', _phone, keyboard: TextInputType.phone),
                _field('Email', _email, keyboard: TextInputType.emailAddress),
                _field('Société', _company),
                _field('Matricule hôte', _hostMatricule, required: true),
                _field('Motif de la visite', _reason, maxLines: 3),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _takePhoto,
                  icon: const Icon(Icons.camera_alt),
                  label: Text(_photo == null
                      ? 'Prendre une photo'
                      : 'Photo capturée ✓'),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _submitting ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Text('Soumettre la demande'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _field(String label, TextEditingController c,
      {bool required = false,
      int maxLines = 1,
      TextInputType keyboard = TextInputType.text}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: TextFormField(
        controller: c,
        maxLines: maxLines,
        keyboardType: keyboard,
        decoration: InputDecoration(
          labelText: label + (required ? ' *' : ''),
          border: const OutlineInputBorder(),
        ),
        validator: (v) {
          if (required && (v == null || v.trim().isEmpty)) {
            return 'Champ requis';
          }
          return null;
        },
      ),
    );
  }
}
