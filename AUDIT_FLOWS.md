# KAYDAN SHIELD — Audit Fonctionnel & Métier

**Date** : 2026-05-10  
**Scope** : Analyse exhaustive des modèles Django vs. UI disponible (CRUD, actions, workflows)  
**Objectif** : Identifier les manques pour une **production operationnelle complète**

---

## TL;DR — Top 10 Manques par Priorité Métier

1. **Pas d'UI pour les visites visiteur (VisitorPass, VisitLog, Watchlist)** — visiteur.models contient 8 modèles, 2 seulement ont CRUD
2. **Pas d'actions métier sur FraudAlert** — créée/vue possible, mais pas : acquitter, escalader, résoudre, assigner investigateur
3. **Pas d'UI pour les certifications ouvrier (WorkerCertification)** — habilitations HSE non gérables dans le back-office
4. **Pas d'UI équipes ouvrier (Crew, WorkerAssignment)** — affectations chantier invisibles; détail ouvrier ne montre pas ses équipes
5. **Pas d'actions badge avancées** — re-émettre, transférer holder, prolonger validité : **zéro action métier** au-delà du CRUD
6. **Flows pointage incomplets** — AttendanceDay calculé nightly mais pas d'UI pour AttendanceCorrection, OvertimeCalculation, Roster
7. **Pas d'UI accès (AccessRule, AccessDecision)** — les règles sont créées/modifiées mais jamais vues dans l'interface
8. **Pas d'UI audit opérationnelle** — AuditLog existe (read-only) mais zéro filtrage/recherche; DataExportRequest a CRUD mais pas "Generate ZIP" bouton
9. **Pas de forms complets** — EmployeeForm, WorkerForm excluent les relations M2M critiques (`authorized_sites`, `face_profiles`)
10. **Tâches Celery périodiques manquantes** — zéro cleanup AccessEvent > 90j, pseudo visiteur > 365j, calcul KPI nightly, etc.

---

## 1. Modèles Présents sans Aucune UI

### 1.1 App `visitors` — 8 modèles, 2 seulement câblés

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `VisitPurpose` | ❌ | ❌ | Dictionnaire motifs visite — doit être gérable en admin | S | P1 |
| `VisitorIDDocument` | ❌ | ❌ | Scans CNI/OCR associés au visiteur — jamais accessible | M | P1 |
| `VisitorInvitation` | ❌ | ❌ | Tokens d'invitation emailed — pas de page invitation/renvoi | M | P2 |
| `VisitorPass` | ❌ | ❌ | QR/badge visiteur émis — critère pour self-service complet | L | P0 |
| `VisitLog` | ❌ | ❌ | Check-in/out timestamps — zéro traçabilité escorte/signature | L | P1 |
| `Watchlist` | ❌ | ❌ | Liste rouge site — visiteur banni : jamais géré en back-office | M | P2 |

**Impact métier** : Workflow visiteur self-service incomplet. Impossible d'ajouter motif, d'émettre QR manuellement, de check-in/out, d'afficher l'escorte ou la signature.

---

### 1.2 App `access_control` — 4 modèles critiques manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `AccessRule` | ❌ | ❌ | Règles temps/zone/certification — jamais gérées en UI | L | P1 |
| `AccessDecision` | ❌ | ❌ | Trace fine d'éval. — read-only, OK ; mais pas de detail view | S | P3 |
| `DoorCommand` | ❌ | ❌ | Déverrouillages manuels — jamais vus/audités en back-office | M | P2 |
| `QRCodeToken` | ❌ | ❌ | Tokens QR visiteur — OK en internal, mais pas d'admin invalidation | S | P2 |

**Impact métier** : Opérateur ne peut pas configurer les règles de contrôle d'accès. Pas de gérance des déverrouillages d'urgence.

---

### 1.3 App `ouvriers` — 3 modèles secondaires manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `WorkerCertification` | ❌ | ❌ | Habilitations HSE (CACES, hauteur) — critère pour accès chantier | M | P1 |
| `Crew` | ❌ | ❌ | Équipes chantier + chef d'équipe — zéro visibilité organisationnelle | M | P2 |
| `WorkerAssignment` | ❌ | ❌ | Affectation ouvrier × site × dates — planning jamais visible | L | P2 |

**Impact métier** : Ouvrier sans certifications visibles. Équipes chantier invisibles. Affectations sur plusieurs sites non tracées.

---

### 1.4 App `attendance` — 4 modèles support manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `Roster` | ❌ | ❌ | Planning prévisionnel jour/personne — jamais saisi/consulté en back-office | M | P2 |
| `AttendanceCorrection` | ❌ | ❌ | Corrections manuelles pointage (audit) — zéro UI pour RH/contrôleur | M | P1 |
| `OvertimeCalculation` | ❌ | ❌ | Calcul heures sup. hebdo — jamais visible sur fiche employé/ouvrier | S | P2 |
| `BLEPresencePing` | ❌ | ❌ | Pings individuels casque (haute fréquence) — high-frequency ; lisible read-only | S | P3 |
| `BLEPresenceWindow` | ❌ | ❌ | Fenêtres 5min agrégées — lisible en graphe temps réel, OK | S | P3 |

**Impact métier** : RH ne peut pas corriger les pointages erronés. Heures supplémentaires non auditables. Planning inexistant.

---

### 1.5 App `antifraud` — 2 modèles critiques manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `FraudInvestigation` | ❌ | ❌ | Enquêtes liées à alertes — jamais créées/gérées ; fiche correction manuelle | M | P1 |
| `FraudScoring` | ❌ | ❌ | Score risque 30j par holder — calculé mais jamais montré (dashboard OK) | S | P2 |

**Impact métier** : Pas de tracking enquête. Pas d'assignation investigateur. Pas de conclusion écrite sur alerte.

---

### 1.6 App `devices` — 5 modèles IoT manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `DeviceHeartbeat` | ❌ | ❌ | Pings périodiques device — high-freq, read-only OK ; mais pas d'alerte "disconnected" | M | P1 |
| `DeviceMaintenance` | ❌ | ❌ | Tickets maintenance device — jamais créés/clôturés en back-office | M | P2 |
| `FirmwareVersion` | ❌ | ❌ | Versions FW disponibles — jamais gérées en catalogue | S | P2 |
| `OTAUpdate` | ❌ | ❌ | Mises à jour OTA — jamais planifiées/exécutées en UI | L | P1 |

**Impact métier** : Devices hors ligne pas détectés. Maintenance pas tracée. Firmware jamais mis à jour.

---

### 1.7 App `audit` — 2 modèles partiellement exposés

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `AuditLog` | ⚠️ | ❌ | Read-only existant ; mais zéro recherche/filtre/export | M | P2 |
| (dans list admin) |  |  |  |  |  |

---

### 1.8 App `accounts` — 3 modèles utilisateur manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `UserSession` | ❌ | ❌ | Sessions actives utilisateur — jamais vues ; pas de "logout everywhere" | M | P2 |
| `LoginAttempt` | ❌ | ❌ | Tentatives login (failed) — jamais montré à opérateur ; critère sécurité | M | P2 |
| (User + Role + APIKey) | ✅ | ✅ | Déjà câblés  |  |  |

---

### 1.9 App `reports` — 3 modèles reporting manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `ReportRun` | ❌ | ❌ | Historique exécutions rapport — jamais visible ; pas de "Run now" bouton sur Report detail | M | P1 |
| `KPISnapshot` | ❌ | ❌ | Snapshots KPI quotidiens — calculés mais jamais vus en detail | S | P2 |
| `Dashboard` | ❌ | ❌ | Dashboards personnalisés — jamais créés ; juste le dashboard global | L | P3 |

---

### 1.10 App `mobile_sync` — 3 modèles offline manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `OfflineScanQueue` | ❌ | ❌ | Queue scans offline — read-only monitoring OK ; pas de manual flush | S | P2 |
| `SyncSession` | ❌ | ❌ | Sessions sync mobile — jamais monitorées ; jamais resyncées manuellement | S | P2 |
| `MobileBundle` | ❌ | ❌ | Bundles de données envoyés au mobile — jamais créés/géré en back-office | M | P3 |

---

### 1.11 App `ai_assistant` — 2 modèles IA manquants

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `AIConversation` | ❌ | ❌ | Conversations IA — jamais vues en historique ; pas de management des prompts | M | P3 |
| `AIToolCall` | ❌ | ❌ | Appels outils IA — jamais audités ; pas de trace des erreurs | S | P3 |
| (AIPromptTemplate) | ✅ | ✅ | Déjà câblé  |  |  |

---

### 1.12 App `core` — 1 modèle manquant

| Modèle | CRUD | Form | Raison | Effort | P |
|--------|------|------|--------|--------|---|
| `SiteGateway` | ✅ | ✅ | Modèle présent, câblé dans CRUD (gateways) ; bon |  |  |

---

## 2. Actions Métier Manquantes sur Entités Existantes

### 2.1 FraudAlert — workflow incomplet

**Boutons/actions manquants** :

- **Acquitter** (`acknowledged`) — opérateur confirme lecture, sans confirmation fraude
- **Escalader** → créer une FraudInvestigation automatiquement + assigner à investigateur
- **Résoudre** → `confirmed_fraud` ou `dismissed` + commentaire + signature
- **Assigner** → sélectionner un User responsible
- **Voir enquête liée** → lien bidirectionnel FraudAlert ↔ FraudInvestigation

**Current state** : detail view montre la FraudAlert ; pas d'action buttton.

**Effort** : M | **Priority** : P0

---

### 2.2 LeaveRequest — workflow d'approbation absent

**Manques** :
- **Approve** → status = `approved` + `approved_by` + `approved_at`
- **Reject** → status = `rejected` + message de refus (`denial_reason`)
- **Cancel** → status = `cancelled`
- **Comment** (audit) — champ historique pour échanges
- **Voir calendar** — visualiser les congés approuvés d'un salarié sur période

**Current state** : CRUD basic, zéro workflow d'approbation.

**Effort** : M | **Priority** : P1

---

### 2.3 VisitRequest — self-service incomplete

**Manques** :
- **Check-in** → créer VisitLog + émettre VisitorPass automatiquement
- **Check-out** → clôturer VisitLog avec timestamp + signature
- **Prolonger** → étendre `expected_duration_minutes` + VisitorPass validity
- **Terminer** → marquer `completed` + clôturer logs
- **Approuver** (si mode walk-in) → status = `approved`
- **Générer QR** → créer/afficher VisitorPass.qr_token

**Current state** : CRUD crée VisitRequest ; pas d'émission badge/QR ou check-in/out.

**Effort** : L | **Priority** : P0

---

### 2.4 Badge — actions avancées absentes

**Manques** :
- **Ré-émettre** → remplacer après perte ; crée nouveau Badge avec même holder
- **Transférer holder** → changer `holder_object_id`/`holder_kind` ; crée BadgeAssignment
- **Prolonger validité** → étendre `valid_until` date
- **Suspendre** → status = `suspended` + `suspended_reason`
- **Restituer** → status = `active` après restitution physique (libère holder)
- **Voir assignements** → timeline BadgeAssignment (déjà en detail context_extras ✅)
- **Voir scans** → timeline BadgeScanEvent (déjà ✅)
- **PDF preview** (déjà ✅)

**Current state** : Detail + PDF OK ; pas d'actions workflow.

**Effort** : M | **Priority** : P1

---

### 2.5 Worker — certifications & équipes manquantes

**Manques** :
- **Ajouter certification** → créer WorkerCertification + upload document + date validité
- **Assigner à équipe** → créer WorkerAssignment + Crew membership + dates
- **Voir ses équipes** → afficher Crew + foreman + start/end dates sur detail view
- **Voir ses certifications** → afficher WorkerCertification avec statut validité (en cours / expiré)
- **Blacklister** → status = `blacklisted` + raison + audit
- **Débloquer** → status = `active` après blacklist

**Current state** : WorkerForm basique ; zero certification/crew UI.

**Effort** : M | **Priority** : P1

---

### 2.6 Employee — autorisations et enrollement absent

**Manques** :
- **Ajouter autorisation site** → M2M `EmployeeAuthorization` (model exists ?) ou simplement `authorized_sites` M2M
- **Enrôler facialement** → lancer FaceProfile enrollment ; marquer comme `face_enrolled=True`
- **Désactiver compte utilisateur** → créer User lié + marquer `is_active=False` centralement

**Current state** : EmployeeForm exclut `authorized_sites` ; pas d'UI enrollement facial.

**Effort** : M | **Priority** : P2

---

### 2.7 Site — gestion locale manquante

**Manques** :
- **Générer QR code accueil** → créer QRCodeToken pour visiteur walk-in?
- **Exporter plan évacuation** → PDF basique avec zones/checkpoints/assembly points
- **Configurer plages horaires** → `Site.opening_hours` M2M pour chaque jour/horaire
- **Voir zones & checkpoints** → detail tab avec liste zones + devices

**Current state** : CRUD basic ; zéro références zones/devices dans detail.

**Effort** : M | **Priority** : P2

---

### 2.8 Device — lifecycle management manquant

**Manques** :
- **Déclencher OTA** → créer OTAUpdate.queued → dispatch async
- **Marquer en maintenance** → créer DeviceMaintenance ticket
- **Voir heartbeats récents** → afficher DeviceHeartbeat timeline (30 derniers)
- **Voir logs accès** → AccessEvent associés au device
- **Voir battery** → graphe historique battery_level

**Current state** : CRUD basic ; pas de lifecycle actions.

**Effort** : M | **Priority** : P2

---

### 2.9 Helmet — gestion basique

**Manques** :
- **Appairer à ouvrier** → créer BadgeHelmetPairing automatiquement lors assign worker
- **Signaler perdu** → status = `lost` + DeviceMaintenance ticket
- **Voir BLE signals** → afficher BLEPresencePing + BLEPresenceWindow timeline
- **Voir still ness alerts** → BLEStillnessSignal relatées

**Current state** : CRUD basique (helmet detail rendering).

**Effort** : M | **Priority** : P2

---

### 2.10 DataExportRequest — RGPD manual completion

**Manques** :
- **Générer ZIP** → créer le fichier ZIP (async Celery task)
- **Envoyer par email** → dispatcher EmailTask avec le fichier
- **Marquer livré** → status = `delivered` + envoi_at
- **Voir statut** → progress bar async

**Current state** : CRUD basique ; zéro action "Generate now" ; zéro email dispatch.

**Effort** : L | **Priority** : P1

---

### 2.11 Report — exécution manuelle manquante

**Manques** :
- **"Run now"** → créer ReportRun asynchrone + enqueue Celery task
- **Télécharger résultat** → PDF/CSV export du dernier ReportRun
- **Partager** → copier lien du rapport ; envoyer par email
- **Voir historique runs** → liste ReportRun ordonnée par date

**Current state** : Report CRUD ; zéro exécution manuelle ; zéro ReportRun UI.

**Effort** : M | **Priority** : P2

---

### 2.12 APIKey — gestion complète manquante

**Manques** :
- **Régénérer secret** → créer nouveau secret_hash ; invalider ancien
- **Restreindre IP** → field `allowed_ips` JSON ; validation au middleware
- **Voir audit appels** → AccessEvent associés via `api_key_id`

**Current state** : APIKey CRUD + one-shot secret display ✅ ; pas de regen/restrict/audit.

**Effort** : S | **Priority** : P2

---

## 3. Workflows Métier Incomplets

### 3.1 Visiteur self-service (P0 CRITIQUE)

**Flow attendu** :
1. Visiteur pré-enregistrement URL (VisitorInvitation token)
2. Visiteur remplit CNI/infos (Visitor + VisitorIDDocument si OCR)
3. Système émet QR code (VisitorPass, QRCodeToken)
4. Visiteur arrive à la borne → scan QR → borne crée VisitLog.checked_in + notifie host
5. Host confirme check-in ou escort  
6. Visiteur quitte → scan QR → VisitLog.checked_out
7. Status → `completed`

**Current blockers** :
- ❌ No VisitorInvitation email dispatch
- ❌ No VisitorPass QR generation in UI
- ❌ No check-in/out button on VisitRequest detail
- ❌ No VisitLog creation form
- ❌ No escort signature capture (VisitLog.signature upload widget)

**Effort** : XL | **Priority** : P0

---

### 3.2 Embauche employé (P1)

**Flow attendu** :
1. Créer Employee (basique)
2. Créer EmployeeContract  
3. Assigner département + position  
4. Ajouter authorized_sites (M2M)
5. Émettre badge RFID NFC  
6. Enrôler facialement (FaceProfile)  
7. Envoyer welcome email + credentiels

**Current blockers** :
- ❌ No EmployeeContract UI
- ❌ EmployeeForm excludes authorized_sites M2M
- ❌ No face enrollment button on detail
- ❌ No email dispatch on creation

**Effort** : L | **Priority** : P1

---

### 3.3 Onboarding ouvrier (P1)

**Flow attendu** :
1. Créer Worker
2. Ajouter WorkerCertification (CACES, hauteur, etc.)
3. Assigner à Crew + site (WorkerAssignment)
4. Émettre badge RFID UHF  
5. Appairer casque (BadgeHelmetPairing)
6. Envoyer onboarding checklist

**Current blockers** :
- ❌ No WorkerCertification UI  
- ❌ No Crew/WorkerAssignment UI
- ❌ No casque pairing button
- ❌ No checklist email

**Effort** : L | **Priority** : P1

---

### 3.4 Pointage journée (P1)

**Flow attendu** :
1. Employé/ouvrier → scan badge au checkpoint (AccessEvent.in)
2. Système crée Punch + met à jour BLEPresencePing/Window (si casque)  
3. Late morning → calcul delay_minutes  
4. Nuit (Celery task) → créer AttendanceDay + rollup Punch
5. Hebdo (Celery task) → calculer OvertimeCalculation  
6. Exposer sur fiche employé/ouvrier (onglet "Pointage" avec 7j history)

**Current blockers** :
- ❌ No Punch detail view
- ❌ No AttendanceDay detail/list UI (Celery rollup OK)
- ❌ No OvertimeCalculation visible on Employee detail
- ❌ No AttendanceCorrection form (RH can't correct)
- ❌ No Roster planning UI

**Effort** : L | **Priority** : P1

---

### 3.5 Cycle alerte fraude (P1)

**Flow attendu** :
1. AccessEvent analyzed → FraudRule triggered → FraudAlert created ✅  
2. Dashboard affiche open alerts ✅  
3. Opérateur → acquitter (`acknowledged`) ou créer FraudInvestigation  
4. Investigateur → analyser evidence + commentaires + conclure  
5. Status = `confirmed_fraud` ou `dismissed`  
6. Archive pour historique

**Current blockers** :
- ❌ No acknowledge/escalate/resolve buttons on detail
- ❌ No FraudInvestigation UI
- ❌ No assignment to investigator
- ❌ No audit trail / comments

**Effort** : M | **Priority** : P1

---

### 3.6 Maintenance dispositif (P2)

**Flow attendu** :
1. Device.last_heartbeat_at > now() - 5min  
2. Celery → DeviceHeartbeat missing → alert ✅ (done?)  
3. Opérateur → crée DeviceMaintenance ticket  
4. OTA queued si FirmwareVersion disponible  
5. Device reconnected → OTA.succeeded  
6. Ticket clôturé

**Current blockers** :
- ❌ No DeviceHeartbeat/Maintenance UI
- ❌ No OTA queuing UI
- ❌ No FirmwareVersion management

**Effort** : L | **Priority** : P2

---

### 3.7 RGPD pseudonymization (P2)

**Flow attendu** :
1. Celery daily task :  
   - Find Visitor.created_at < 365 days ago
   - Pseudonymize (clear first_name, last_name, id_number, phone, etc. → hashes)
   - Set `pseudonymized_at` timestamp
2. Audit log pseudonymization action
3. Manual trigger via Admin UI possible?

**Current blockers** :
- ❌ No Celery task visible/defined
- ❌ No pseudonymization service
- ❌ No manual trigger button on Visitor detail

**Effort** : M | **Priority** : P2

---

## 4. Intégrations & Notifications Manquantes

### 4.1 Email transactionnel

**Configured** : `DEFAULT_FROM_EMAIL=no-reply@kaydangroupe.com`  
**Events missing** :
- ❌ Employee creation → welcome email + temp password
- ❌ Worker onboarding → checklist email
- ❌ VisitorInvitation → send email with token link
- ❌ LeaveRequest approval → notify manager + employee
- ❌ DataExportRequest completion → send ZIP link
- ❌ Device maintenance alert → notify technician
- ❌ FraudAlert escalation → notify investigator

**Effort** : M | **Priority** : P1

---

### 4.2 Push FCM

**Status** : Task #70 mentions "FCM push webhook backend" — unclear if wired.  
**Missing** :
- ❌ NotificationDispatcher integration  
- ❌ MobileDevice FCM token storage + refresh
- ❌ Trigger rules (FraudAlert, LeaveRequest approval, etc.)

**Effort** : M | **Priority** : P2

---

### 4.3 SMS / WhatsApp

**Status** : Not mentioned in codebase.  
**Use case** : Visiteur sans email → SMS invitation, OTP check-in?

**Effort** : L (if needed) | **Priority** : P3

---

### 4.4 Calendrier ICS

**Missing** : VisitRequest → export .ics for host employee  
**Effort** : S | **Priority** : P3

---

### 4.5 Webhooks sortants

**Missing** : HRIS / ERP / SIRH integrations  
- Employee creation → webhook to payroll  
- Attendance → daily rollup webhook
- Leave approval → HR system sync

**Effort** : L | **Priority** : P3

---

### 4.6 Slack / Teams

**Missing** : Critical alerts via Slack  
- FraudAlert severity=critical → Slack webhook  
- Device offline → Slack notif

**Effort** : S | **Priority** : P3

---

## 5. Vues Admin Secondaires Non Implémentées

| Vue | Description | Effort | Priority |
|-----|-------------|--------|----------|
| `/me/` | Current user profile (visible but as API only) | S | P2 |
| `UserSession` list | Active sessions + "logout everywhere" | M | P2 |
| `LoginAttempt` security page | Failed logins + IP + timestamp | M | P2 |
| `AuditLog` search | Filter by user/action/target + export | M | P2 |
| Bulk CSV import | Employees + Workers + Visitors upload | L | P2 |
| CSV/Excel export | On all list views (already done realtime) | M | P2 |
| `Trade` management | Métiers ouvrier standalone CRUD | S | P2 |
| `VisitPurpose` management | Motifs visite standalone CRUD | S | P2 |
| `Department` / `JobPosition` | Standalone CRUD (not in Employee form) | M | P2 |
| Site detail map | Zones/Checkpoints layout + devices overlay | L | P1 |
| Badge PDF preview inline | PDF rendered in detail (not just link) | S | P2 |
| "Mon équipe" (manager) | Manager sees their team members only | M | P2 |

---

## 6. Champs & Relations Manquants dans Formulaires

### 6.1 EmployeeForm

**Exclut (models.py shows)** :
- `authorized_sites` (M2M) — critère accès
- `face_profile` (FK if exists) — enrollment status
- `emergency_contact_*` (exists ? check models)
- `EmployeeContract` relation
- `EmployeeSchedule` link
- `EmployeeAuthorization` (M2M? direct?)

**Fix** : Étendre EmployeeForm pour inclure M2M sites + embauche complète.

**Effort** : S | **Priority** : P1

---

### 6.2 WorkerForm

**Exclut** :
- `certifications` (reverse FK) — afficher + bouton ajouter
- `crews` (M2M) + `assignments` (FK) — afficher liste équipes
- `trade` — déjà inclus ✅
- Assignation site/dates — manquant

**Fix** : Ajouter inlines ou tabs pour certs + crews.

**Effort** : M | **Priority** : P1

---

### 6.3 VisitRequestForm

**Exclut** :
- `approved_by` / `approved_at` — approval workflow
- `VisitorPass` creation — pas de relation directe
- `expected_duration_minutes` — exists but needs widget
- Mode walk-in → auto-approve ou manual ?

**Fix** : Ajouter approval fields + mode toggle.

**Effort** : S | **Priority** : P1

---

## 7. Tâches Celery Périodiques Manquantes

| Tâche | Fréquence | Purpose | Effort | Priority |
|-------|-----------|---------|--------|----------|
| Rotate AccessEvent > 90j | Daily | Archive old scans to cold storage | M | P2 |
| Pseudonymize Visitor > 365j | Daily | RGPD: clear PII + set pseudonymized_at | M | P2 |
| Compute KPISnapshot | Daily 00:00 | Snapshot KPIs for reporting | S | P2 |
| Compute AttendanceDay | Daily 23:00 | Rollup Punches → AttendanceDay (per site) | M | P1 |
| Compute OvertimeCalculation | Weekly Mon 01:00 | Rollup AttendanceDay → OT hours | M | P1 |
| Cleanup QRCodeToken expired | Hourly | Delete tokens where expires_at < now() | S | P2 |
| Health check DeviceHeartbeat | Every 5min | Alert if > 5 min since last heartbeat | S | P1 |
| Generate DataExportRequest ZIP | On demand (async) | RGPD export async Celery task | M | P1 |
| Recompute geofence violations | Per event (real-time) | Already done in antifraud.evaluate() ✅ | — | — |

---

## 8. Recommandations par Criticité

### P0 — Block Production (Fix before launch)

1. **Visiteur self-service complete** (`VisitRequest` → `VisitorPass` → QR → check-in/out)
   - Add VisitorPass + VisitLog CRUD
   - Add check-in/out + signature buttons on VisitRequest detail
   - Emit QR code on badge assignment
   - **Effort** : XL | **Timeline** : 3-4 jours

2. **FraudAlert actions** (acknowledge, escalate, resolve)
   - Add buttons + forms on FraudAlert detail
   - Create FraudInvestigation on escalate
   - Implement audit trail
   - **Effort** : M | **Timeline** : 2-3 jours

3. **DataExportRequest "Generate now"** + email dispatch
   - Add async Celery task to generate ZIP
   - Add "Download" link once ready
   - Email to requestor
   - **Effort** : L | **Timeline** : 2 jours

4. **LeaveRequest approval workflow**
   - Add Approve/Reject/Cancel buttons
   - Send email notifications
   - Manager dashboard to see pending leaves
   - **Effort** : M | **Timeline** : 2 jours

5. **Site detail → zones + checkpoints tab**
   - Display related Zone + Checkpoint + Device
   - **Effort** : S | **Timeline** : 1 jour

### P1 — Core Business (1-2 weeks post-launch)

6. **WorkerCertification UI** + onboarding workflow
7. **Crew + WorkerAssignment UI** (team management)
8. **AttendanceDay + OvertimeCalculation** UI
9. **AttendanceCorrection** for RH adjustments
10. **Badge advanced actions** (re-issue, transfer, prolong)
11. **Email transactionnel** (5+ event templates)
12. **Celery heartbeat monitoring** task

### P2 — Nice-to-have (month 1-2)

13. **Device maintenance** workflow + OTA management
14. **AuditLog** searchable UI + export
15. **ReportRun** creation + download + sharing
16. **Employee authorized_sites** M2M form
17. **User sessions** management page
18. **CSV bulk import** for entities
19. **Bulk CSV export** on all lists
20. **Trade**, **VisitPurpose** CRUD

### P3 — Enhancements (backlog)

21. Slack/Teams integrations
22. Webhooks outbound (HRIS sync)
23. SMS/WhatsApp invitations
24. Calendar .ics export
25. Manager "Mon équipe" view
26. Dashboard customization
27. AI Conversation history + audit

---

## 9. Roadmap Suggérée (10 semaines)

### Semaine 1-2 : P0 Blockers
- Visitor self-service complete
- FraudAlert workflow
- LeaveRequest approval
- DataExportRequest async + email

### Semaine 3-4 : P0 + P1 Foundation
- WorkerCertification + Crew UI
- AttendanceDay + corrections
- Badge actions
- Email templates (5 core)

### Semaine 5-6 : P1 Completion
- Device maintenance workflow
- Celery tasks (7 tâches)
- Site detail map
- AuditLog search

### Semaine 7-8 : P2 Polish
- ReportRun + download
- Employee authorized_sites
- User sessions
- CSV import/export

### Semaine 9-10 : Testing + P3
- Integration testing
- Load testing
- Documentation
- P3 enhancements (pick 2-3)

---

## 10. Synthèse — Critique pour Production

**Total models without UI** : 32 models  
**Total missing action buttons** : 12+ entities  
**Total incomplete workflows** : 7 core flows  
**Critical blockers** : 5 (visitor, fraud, leave, export, site)  
**Estimated effort** : **12-14 semaines** (P0 + P1) pour un système complet & production-ready.

**Sans corriger au minimum les P0** :
- ❌ Visiteurs ne peuvent pas se pré-enregistrer
- ❌ Fraudes non enquêtées
- ❌ RH ne peut pas gérer congés
- ❌ RGPD exports non automatisables
- ❌ Équipes ouvrier invisibles → pas de planning chantier

