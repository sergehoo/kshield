# KAYDAN SHIELD — Modèles & Services par Couche Métier

> Solution de contrôle d'accès intelligent — Bureaux • Chantiers • Zones de Stockage
> Document d'architecture fonctionnelle et technique
> Stack : Django 4.2 · DRF · Channels · Celery · PostgreSQL · Redis · MinIO/S3

---

## 1. Vue d'ensemble en couches

L'architecture suit une séparation stricte en 5 couches, chacune portée par un sous-ensemble d'apps Django :

| Couche | Rôle | Apps Django |
|---|---|---|
| **Socle** | Multi-tenant, comptes, sites, RBAC | `core`, `accounts`, `sites` |
| **Identité métier** | Personnes physiques contrôlées | `employees`, `ouvriers`, `visitors` |
| **Terrain** | Équipements, badges, casques, bornes | `devices` |
| **Contrôle d'accès & Pointage** | Événements, scans, présence, règles | `access_control`, `attendance` |
| **Sécurité & Pilotage** | Anti-fraude, alertes, audit, reporting, sync mobile | `antifraud`, `notifications`, `audit`, `reports`, `mobile_sync` |
| **IA (optionnelle)** | Assistant conversationnel, RAG, function calling | `ai_assistant` *(nouvelle app à créer)* |

Chaque app expose : `models.py`, `services.py` (logique métier orchestrée), `selectors.py` (lectures complexes), `serializers.py` (DRF), `views.py` (API + UI), `tasks.py` (Celery), `signals.py`, `permissions.py`, `consumers.py` (WebSocket si applicable).

---

## 2. Couche Socle

### 2.1 `core` — Fondations transversales

**Objectif** : multi-tenant (KAYDAN Groupe → filiales), modèles abstraits, infrastructure transversale.

**Modèles**
- `Tenant` — KAYDAN Groupe et filiales (ex : KAYDAN BTP, KAYDAN Logistique). Champs : nom, code, logo, fuseau horaire, devise, statut.
- `Company` (Filiale) — rattachée à un `Tenant`. Champs : raison sociale, IFU, secteur, adresse, contact référent.
- `TimeStampedModel` (abstrait) — `created_at`, `updated_at`, `created_by`, `updated_by`.
- `SoftDeleteModel` (abstrait) — `is_deleted`, `deleted_at`, `deleted_by` (gestion RGPD).
- `Address` — réutilisable (sites, visiteurs, etc.).
- `FeatureFlag` — activation par tenant des modules optionnels (chatbot IA, OCR avancé, BLE, etc.).

**Services**
- `TenantContextService` — résolution du tenant courant via middleware (sous-domaine ou JWT claim).
- `AuditableMixin` — hook automatique vers `audit.AuditLogService` à chaque save/delete.
- `FeatureFlagService.is_enabled(tenant, flag)`.

### 2.2 `accounts` — Utilisateurs et RBAC

**Objectif** : utilisateurs back-office, rôles métier, sécurité d'authentification.

**Modèles**
- `User` (AbstractUser) — email comme identifiant, MFA, dernière IP, photo. Lié à `Tenant` et `Company`.
- `Role` — Super Admin, Admin Tenant, Manager Site, Agent de Pointage, Contrôleur Travaux, Gardien, RH, Auditeur, Lecture Seule.
- `Permission` (custom) — granulaire par module (ex : `attendance.view_punch`, `antifraud.acknowledge_alert`).
- `RoleAssignment` — User × Role × Site (un même user peut être Manager sur Site A et Lecteur sur Site B).
- `UserSession` — sessions actives, device fingerprint, dernière activité.
- `LoginAttempt` — historique des tentatives, anti-bruteforce.
- `APIKey` — pour terminaux fixes / passerelles IoT (rotation, scopes).

**Services**
- `AuthService.login(email, password, mfa_code)` — émet JWT + refresh.
- `RBACService.user_can(user, perm, scope=site)` — résolution permission.
- `SessionService.revoke_all(user)` — déconnexion globale.
- `APIKeyService.issue/rotate/revoke`.

### 2.3 `sites` — Sites, zones, points de contrôle

**Objectif** : modélisation physique des lieux contrôlés.

**Modèles**
- `Site` — bureau, chantier, entrepôt. Champs : nom, type (`office | warehouse | construction`), company, adresse, coordonnées GPS, périmètre (geofence GeoJSON), statut, fuseau, horaires d'ouverture par défaut, date début/fin (chantier).
- `Zone` — sous-zone d'un site (Bâtiment A, Hall principal, Stockage froid, Tour 3 niveau R+5). Hiérarchie parent/enfant.
- `Checkpoint` — point de contrôle physique : type (`entry | exit | bidirectional | inopiné`), mode (`fixe | mobile`), zone, équipement attaché.
- `OpeningHours` — plages horaires par site/zone (matin, après-midi, nuit, week-end, jours fériés).
- `SitePolicy` — règles par site : tolérance retard, pause obligatoire, casque obligatoire, ouvert public, horaires limites pointage matin/soir.
- `WorkSiteProject` (sous-classe `Site` pour chantier) — chef de chantier, contrôleur travaux principal, météo critique, niveau de risque.

**Services**
- `SiteRoutingService.find_active_checkpoint(zone, time)`.
- `GeofenceService.is_inside(site, lat, lng)`.
- `OpeningHoursService.is_open(site, datetime)`.

---

## 3. Couche Identité Métier

### 3.1 `employees` — Personnel administratif et stockage (Segment EMPLOYÉS)

**Objectif** : annuaire RH des employés porteurs de badges NFC.

**Modèles**
- `Department` — direction, service, équipe.
- `JobPosition` — fonction, niveau hiérarchique.
- `Employee` — matricule, nom, prénom, photo, email pro, téléphone, company, département, poste, statut contrat (`CDI | CDD | Stage | Intérim`), date d'embauche, date de fin, manager, sites autorisés (M2M), photo d'identité (S3), pièce CNI, signature numérique.
- `EmployeeContract` — historique contractuel (avenants, mutations).
- `EmployeeAuthorization` — habilitations spécifiques (zone confidentielle, accès stockage classé).
- `EmployeeSchedule` — horaire théorique (équipe matin/soir/nuit, télétravail).

**Services**
- `EmployeeOnboardingService.create(payload, photo, badge_uid)` — orchestration : création, génération badge NFC, envoi mail bienvenue.
- `EmployeeOffboardingService.terminate(employee, end_date)` — désactivation badge, révocation accès, scellement données.
- `EmployeeRosterService.expected_today(site)` — qui est attendu aujourd'hui.

### 3.2 `ouvriers` — Personnel chantier (Segment OUVRIERS)

**Objectif** : ouvriers de chantier équipés du couple Badge RFID UHF + Casque connecté.

**Modèles**
- `Trade` (Métier/Corps de métier) — maçon, électricien, ferrailleur, conducteur engin, etc.
- `Worker` (Ouvrier) — matricule, nom, prénom, date de naissance, photo, CNI/passeport, contact urgence, métier, sous-traitant, certifications HSE, taille casque, statut (`actif | suspendu | sortie`).
- `Subcontractor` (Sous-traitant) — entreprise externe employant des ouvriers, contact, contrat cadre.
- `WorkerAssignment` — affectation ouvrier × chantier × période (date début/fin, équipe, contrôleur référent).
- `WorkerCertification` — habilitations HSE (CACES, travail en hauteur, électricité). Date d'expiration → blocage automatique.
- `Crew` (Équipe) — groupe d'ouvriers + chef d'équipe, sur un chantier.

**Services**
- `WorkerEnrollmentService.enroll(worker, badge_uid, helmet_uid, site)` — initialise l'appairage badge/casque pour le chantier.
- `WorkerAssignmentService.move(worker, from_site, to_site)`.
- `CertificationService.check_validity(worker, work_type)` — bloque l'accès si certif expirée.

### 3.3 `visitors` — Visiteurs (Segment VISITEURS)

**Objectif** : gestion des deux modes — inopiné (OCR CNI) et self-service (QR planifié).

**Modèles**
- `Visitor` — identité extraite (nom, prénom, date naissance, nationalité, n° pièce, type pièce). Données pseudonymisées après TTL configurable (RGPD).
- `VisitPurpose` — choix : visite de site, RDV commercial, RDV responsable, RDV direction, invitation, autre.
- `VisitRequest` — demande de visite : visiteur, hôte (Employee), site, motif, date prévue, durée, statut (`pending | approved | rejected | cancelled | completed`).
- `VisitorPass` (Badge visiteur) — type (`self_service_qr | walk_in_pvc`), code QR, badge visuel, validité (datetime début/fin), zones autorisées.
- `VisitorIDDocument` — image recto/verso CNI (chiffrée S3), résultat OCR brut JSON, score de confiance OCR.
- `VisitLog` — entrée effective : check-in datetime, check-out datetime, gardien check-in, escort employee, signature.
- `Watchlist` (Liste rouge) — interdictions ponctuelles (visiteur banni d'un site).
- `VisitorInvitation` — token + lien envoyé par email/SMS au visiteur en mode self-service.

**Services**
- `VisitorOCRService.extract(image)` — appel moteur OCR (Tesseract + Mindee fallback), retourne `{nom, prénom, date_nais, n°pièce, score}`.
- `VisitorPreRegistrationService.create_invitation(host, visitor_email, date)` — génère token, envoie mail + lien formulaire.
- `VisitorCheckInService.walk_in(site, id_document, host_employee, guard_user)` — workflow inopiné complet.
- `VisitorCheckInService.self_service(qr_token)` — workflow QR.
- `VisitorCheckOutService.checkout(visit_log)` — clôture, calcul durée, libération badge.
- `WatchlistService.is_banned(visitor, site)`.

---

## 4. Couche Terrain

### 4.1 `devices` — Équipements physiques

**Objectif** : inventaire et état de santé de tout équipement déployé.

**Modèles**
- `DeviceModel` — référence catalogue (Chainway UR4, Chainway C72, Xerafy Micro X II, MOKOSmart H7, Samsung Tab Active4, lecteur NFC mural, gâche électrique, scanner CNI). Champs : marque, modèle, type (`reader_uhf_fixed | reader_uhf_mobile | reader_nfc_fixed | reader_nfc_mobile | tag_uhf | beacon_ble | tablet | id_scanner | door_lock`), spec JSON.
- `Device` — instance physique : numéro de série, modèle, site rattaché, zone, statut (`active | inactive | maintenance | lost`), date de mise en service, dernière heartbeat, IP/MAC, version firmware, niveau batterie.
- `Badge` — badge NFC (employés/visiteurs PVC) ou tag RFID UHF (ouvriers). Champs : UID, type (`nfc | uhf`), porteur (GenericForeignKey vers Employee/Worker/Visitor), statut (`active | lost | revoked | expired`), date émission/expiration.
- `Helmet` (Casque connecté) — référence physique : tag UHF UID + beacon BLE UID, date mise en service, statut, ouvrier actuellement apparié (nullable).
- `BadgeHelmetPairing` — historique d'appairages quotidiens : worker, badge, helmet, date, premier scan matin, vérifications successives.
- `DeviceHeartbeat` — ping périodique : timestamp, état (online/offline), batterie, signal, RAM/CPU.
- `DeviceMaintenance` — interventions, pannes, remplacements.
- `FirmwareVersion` & `OTAUpdate` — déploiement OTA piloté.

**Services**
- `DeviceProvisioningService.register(serial, site, api_key)` — enrôlement nouveau terminal.
- `BadgeIssuanceService.issue(holder, type)` — émission, impression PVC, association.
- `BadgeRevocationService.revoke(badge, reason)` — invalide en temps réel (push aux terminaux).
- `HelmetPairingService.start_day(worker, badge_uid, helmet_uid, site)` — création de l'appairage du jour.
- `HelmetPairingService.verify(badge_uid, helmet_uid, scan_time)` — vérifie cohérence ; déclenche `antifraud` si KO.
- `DeviceHealthService.heartbeat(device, payload)` — met à jour, alerte si silence > seuil.

---

## 5. Couche Contrôle d'Accès & Pointage

### 5.1 `access_control` — Événements d'accès et règles

**Objectif** : capture brute de chaque scan et décision d'accès (autoriser, refuser, alerter).

**Modèles**
- `AccessEvent` (table très volumineuse, partitionnée par mois) — id, timestamp, site, zone, checkpoint, device, badge_uid, helmet_uid, holder (GenericForeignKey), direction (`in | out | pass`), method (`nfc | uhf | ble | qr | manual`), decision (`granted | denied | review`), denial_reason, raw_payload JSON, latitude/longitude (mobile), agent_user (si scan opéré par humain).
- `AccessRule` — règles déclaratives : ex « ouvrier doit avoir casque apparié », « visiteur uniquement zone hall », « employé hors horaires → alerte ». Type (`time_window | zone_authorization | pairing_required | certification_required | escort_required`), conditions JSON, sévérité, actions.
- `AccessDecision` — trace de l'évaluation : règles évaluées, règle ayant tranché, score risque.
- `DoorCommand` — commande envoyée à une gâche électrique (`unlock | lock`), résultat, latence.
- `QRCodeToken` — pour visiteurs self-service : token signé (HMAC), payload, expiration, usage unique ou multiple.

**Services**
- `AccessGatewayService.process_scan(payload)` — point d'entrée unique appelé par tous les terminaux. Pipeline :
  1. Authentification terminal (API key)
  2. Résolution porteur (badge → Employee/Worker/Visitor)
  3. Vérification statut badge & holder
  4. Évaluation `AccessRulesEngine`
  5. Pour ouvrier : appel `HelmetPairingService.verify`
  6. Décision + persistance `AccessEvent` + `AccessDecision`
  7. Émission événement WebSocket dashboard
  8. Émission tâches asynchrones : `notifications`, `antifraud.scan`, `attendance.consume_event`
- `AccessRulesEngine.evaluate(context)` — moteur de règles configurable par site.
- `DoorControlService.unlock(checkpoint, reason)` — pilote la gâche, audit.
- `QRTokenService.issue(visit_request)` / `validate(token)`.

### 5.2 `attendance` — Pointage et présence

**Objectif** : agrégation des `AccessEvent` en présence quotidienne, calcul retards/absences.

**Modèles**
- `Punch` — vue logique d'un pointage (matin / soir / pause). Construit à partir d'AccessEvent par règle métier. Champs : holder, site, date, type (`morning_in | morning_out | evening_in | evening_out | break_in | break_out`), source_event, retard_minutes, statut (`on_time | late | very_late | missing`).
- `AttendanceDay` — journée consolidée : holder, site, date, premier_pointage, dernier_pointage, durée_présence, statut (`present | partial | absent | leave | rest_day`), retard_total_minutes, casque_apparié (bool), incidents_count.
- `BLEPresencePing` — ping continu BLE journée (ouvriers) : helmet, zone détectée, timestamp, RSSI, accéléromètre (immobile bool).
- `BLEPresenceWindow` — fenêtre agrégée (par 5 min) : helmet, zone, premier/dernier ping, immobile_minutes.
- `LeaveRequest` — congé, maladie, mission externe : holder, type, date début/fin, statut, document justificatif.
- `Roster` — planning prévisionnel : holder, site, date, équipe, heures attendues.
- `OvertimeRule` & `OvertimeCalculation` — heures supplémentaires.
- `AttendanceCorrection` — correction manuelle par RH/manager avec justification (audit).

**Services**
- `PunchBuilderService.consume(access_event)` — convertit un `AccessEvent` en `Punch` (logique matin vs soir vs pause).
- `AttendanceDayService.recompute(holder, date)` — agrège pointages + BLE en `AttendanceDay`.
- `BLEPresenceService.ingest(ping_batch)` — bulk insert des pings, agrège en fenêtres.
- `LateService.evaluate(punch, policy)` — applique tolérance site → statut.
- `AbsenceDetectorService.run_daily(site, date)` — détecte les ouvriers attendus mais absents (job Celery 18h).
- `OvertimeService.compute_week(holder, week)`.
- `AttendanceCorrectionService.apply(user, day, override, reason)` — trace l'audit.

---

## 6. Couche Sécurité & Pilotage

### 6.1 `antifraud` — Détection de fraude multi-couches

**Objectif** : implémentation des 4+ scénarios de fraude documentés (badge prêté, casque posé, départ après pointage, échange casques).

**Modèles**
- `FraudRule` — règle déclarative : code (ex `BADGE_HELMET_MISMATCH`), libellé, sévérité (`info | warning | critical`), seuil/paramètres, état actif.
- `FraudAlert` — alerte levée : règle, holder principal, holder secondaire (en cas d'échange), site, evidence JSON (events liés, snapshots), statut (`open | acknowledged | confirmed | dismissed | escalated`), assigné_à, datetime levée, datetime résolution, commentaire résolution.
- `FraudInvestigation` — dossier d'enquête regroupant plusieurs alertes liées à un même holder/incident, avec pièces jointes.
- `FraudScoring` — score de risque par holder (rolling 30 jours).
- `BLEStillnessSignal` — détection de casque immobile (>30 min) consommée par règle dédiée.

**Règles fournies**
| Code | Description | Sources |
|---|---|---|
| `BADGE_HELMET_MISMATCH` | Badge UHF #X sans casque #X au scan | `access_control` |
| `HELMET_LEFT_UNATTENDED` | Casque immobile > 30 min | `BLEPresencePing` + accéléro |
| `WORKER_LEFT_AFTER_MORNING` | Pointage matin OK mais casque non détecté toute la journée | `BLEPresenceWindow` |
| `HELMET_SWAP` | Appairage soir ≠ appairage matin | `BadgeHelmetPairing` |
| `BADGE_TWICE_DIFFERENT_ZONES` | Même badge scanné simultanément à 2 endroits | `AccessEvent` |
| `EXPIRED_CERTIFICATION` | Ouvrier scanne avec certif expirée | `WorkerCertification` |
| `OUT_OF_HOURS_ACCESS` | Accès hors plage autorisée | `OpeningHours` |
| `WATCHLIST_HIT` | Visiteur sur liste rouge | `Watchlist` |

**Services**
- `FraudEngineService.evaluate_event(access_event)` — appelé en async après chaque scan ; exécute les règles UHF.
- `FraudEngineService.evaluate_ble_window(window)` — évalue les règles BLE.
- `FraudAlertService.raise(rule, evidence)` — crée alerte + déclenche `notifications`.
- `FraudAlertService.acknowledge / confirm / dismiss / escalate`.
- `FraudScoringService.recompute(holder)` — score quotidien (job Celery).

### 6.2 `notifications` — Alertes & messages multi-canaux

**Objectif** : router les notifications utilisateurs et terminaux.

**Modèles**
- `NotificationTemplate` — code, canal, sujet, corps (Jinja-like), variables.
- `NotificationChannel` — `inapp | email | sms | push | webhook | whatsapp`.
- `NotificationPreference` — préférences par user (canaux opt-in).
- `Notification` — instance émise : recipient, template, channel, payload, statut (`queued | sent | delivered | failed | read`), provider response.
- `WebSocketSubscription` — abonnements (user + topic, ex : `site:42:alerts`).

**Services**
- `NotificationDispatcher.send(template_code, recipient, context)` — résout préférences, route vers le bon backend.
- `EmailBackend / SMSBackend / PushBackend / WhatsAppBackend` — implémentations.
- `RealtimeBroadcaster.broadcast(channel, event)` — push WebSocket via Channels (groupes Redis).
- `DigestService.daily_supervisor_digest(site)` — récap journalier.

### 6.3 `audit` — Journal d'audit & traçabilité

**Objectif** : journal immuable de toutes les actions sensibles (RGPD, conformité, contentieux).

**Modèles**
- `AuditLog` — id, user, tenant, action (`create | update | delete | login | export | acknowledge | override | unlock_door`), target_model, target_id, before JSON, after JSON, ip, user_agent, datetime, hash_chaîné (preuve d'intégrité).
- `DataExportRequest` — demande RGPD (export ou suppression), holder, statut, fichier généré (chiffré).
- `LegalRetentionPolicy` — politique de rétention par type de donnée.
- `ConformityRegister` — registre de conformité : visites, exercices d'évacuation, contrôles obligatoires.

**Services**
- `AuditLogService.log(user, action, target, before, after)` — appelé par mixin générique.
- `IntegrityService.verify_chain(start, end)` — vérifie la chaîne de hashes.
- `RGPDService.export_user_data(holder)` / `forget(holder)`.

### 6.4 `reports` — Statistiques, KPI, exports

**Objectif** : reporting opérationnel et stratégique.

**Modèles**
- `Report` — définition : nom, type (`tabular | chart | dashboard`), requête (paramétrée), périmètre.
- `ReportRun` — exécution : auteur, paramètres, statut, fichier généré (PDF/XLSX/CSV), expire_at.
- `ReportSchedule` — planification (Celery Beat) avec destinataires.
- `KPISnapshot` — agrégations quotidiennes pré-calculées : présence_taux, retards_moyens, alertes_count par site/date.
- `Dashboard` & `DashboardWidget` — tableaux de bord configurables.

**Services**
- `ReportService.run(report, params, user)` — exécution sandboxée (timeouts, quota).
- `KPIComputeService.recompute_day(date)` — job Celery 23h.
- `ExportService.to_xlsx / to_pdf / to_csv` — utilise WeasyPrint, openpyxl, tablib.

### 6.5 `mobile_sync` — API mobile et offline

**Objectif** : terminaux mobiles (Chainway C72, tablettes, smartphones agents pointage / chefs d'équipe / gardiens) en mode dégradé.

**Modèles**
- `MobileDevice` — terminal mobile enrôlé : user, device_id, os, app_version, last_sync, statut.
- `OfflineScanQueue` — scans capturés hors ligne, en attente de sync : payload, signature, créé_at, synced_at.
- `SyncSession` — session de synchronisation : start, end, items_pulled, items_pushed, conflicts.
- `MobileBundle` — paquet de données poussées au terminal (badges autorisés, règles, watchlist, photos employés cache).

**Services**
- `MobileAuthService` — pairing par code QR + API key.
- `BundleBuilderService.build(device, since)` — construit le delta à pousser.
- `OfflineIngestService.flush(device, batch)` — relit les scans offline, applique idempotence (dedupe par UUID), pipeline normal `AccessGatewayService`.
- `ConflictResolutionService` — stratégie last-writer-wins horodaté avec audit.

---

## 7. Couche IA — Assistant Kaydan (transversale)

> Activable via `FeatureFlag('ai_assistant')`. S'appuie sur `openai` (déjà dans `requirements.txt`).

**Modèles** (app `core` ou nouvelle app `ai_assistant`)
- `AIConversation` — user, titre, started_at, contexte (site, période).
- `AIMessage` — role (`user | assistant | system | tool`), contenu, tokens, datetime.
- `AIToolCall` — outil invoqué (ex `attendance.late_today`, `antifraud.open_alerts`), arguments, résultat, latence.
- `AIPromptTemplate` — bibliothèque de prompts par rôle métier (RH, contrôleur, gardien).

**Services**
- `AIChatService.ask(user, question, context)` — orchestration RAG + function calling.
- `AIToolRegistry` — outils exposés à l'IA :
  - `get_attendance_summary(site, date)`
  - `list_open_fraud_alerts(site)`
  - `find_employee(query)`
  - `unlock_door(checkpoint)` *(soumis à confirmation utilisateur)*
  - `generate_report(report_id, params)`
- `AIGuardrailService` — filtrage prompt injection, redaction PII, quotas par user.

---

## 8. Flux de bout en bout (exemple ouvrier)

```
06:42  Borne UR4 lit Badge_X + Helmet_X simultanément (< 1 s)
   └─> POST /api/access/scan {device_id, badge_uid, helmet_uid, ts}
       AccessGatewayService.process_scan
       ├─> resolve(badge_uid) -> Worker
       ├─> HelmetPairingService.verify(badge, helmet)  [première fois du jour → start_day]
       ├─> AccessRulesEngine.evaluate -> granted
       ├─> save AccessEvent (decision=granted)
       ├─> save Punch(morning_in)
       ├─> RealtimeBroadcaster.broadcast("site:42:scans", {...})
       └─> Celery: antifraud.evaluate_event, notifications.notify_supervisor

10:15  BLE ping reçu (helmet immobile depuis 32 min)
   └─> BLEPresenceService.ingest -> BLEStillnessSignal
       └─> FraudEngineService.evaluate_ble_window
           └─> FraudAlertService.raise(HELMET_LEFT_UNATTENDED)
               ├─> WebSocket push dashboard
               └─> SMS contrôleur travaux

17:48  Borne UR4 lit Badge_X + Helmet_Y  (échange casque)
   └─> AccessGatewayService.process_scan
       └─> HelmetPairingService.verify -> mismatch
           └─> FraudAlertService.raise(HELMET_SWAP, both_workers)
```

---

## 9. Endpoints API (extrait, DRF + drf-spectacular)

| Méthode | URL | Service |
|---|---|---|
| `POST` | `/api/v1/auth/login` | AuthService |
| `POST` | `/api/v1/access/scan` | AccessGatewayService |
| `GET`  | `/api/v1/access/events` | filtered list |
| `POST` | `/api/v1/visitors/walk-in` | VisitorCheckInService.walk_in |
| `POST` | `/api/v1/visitors/self-service/{token}` | self_service |
| `GET`  | `/api/v1/attendance/days?site=&date=` | AttendanceDayService |
| `GET`  | `/api/v1/antifraud/alerts` | FraudAlert list |
| `POST` | `/api/v1/antifraud/alerts/{id}/acknowledge` | FraudAlertService |
| `POST` | `/api/v1/mobile/sync/pull` | BundleBuilderService |
| `POST` | `/api/v1/mobile/sync/push` | OfflineIngestService |
| `POST` | `/api/v1/ai/chat` | AIChatService |
| `WS`   | `/ws/dashboard/site/{id}` | RealtimeBroadcaster |

---

## 10. Tâches Celery clés

| Tâche | Fréquence | App |
|---|---|---|
| `attendance.recompute_day` | toutes les 5 min (incrémental) | attendance |
| `attendance.detect_absences` | 18h00 | attendance |
| `antifraud.scan_ble_windows` | toutes les minutes | antifraud |
| `antifraud.recompute_scoring` | 02h00 | antifraud |
| `notifications.daily_digest` | 19h00 | notifications |
| `reports.kpi_snapshot` | 23h45 | reports |
| `audit.verify_chain` | hebdomadaire | audit |
| `devices.health_sweep` | toutes les 2 min | devices |
| `mobile_sync.purge_old_bundles` | quotidien | mobile_sync |

---

## 11. Sécurité & Conformité

- **Chiffrement** : pièces d'identité visiteurs chiffrées au repos (KMS / Fernet), TLS bout-en-bout.
- **RGPD / loi 2013-450 Côte d'Ivoire** : politique de rétention par type, droit d'accès et d'effacement (`RGPDService`).
- **Auditabilité** : chaîne de hashes sur `AuditLog`, exports immuables.
- **MFA** obligatoire pour rôles Admin & Auditeur.
- **Anti-bruteforce** : `LoginAttempt` + lock progressif.
- **API terminaux** : signature HMAC + rotation de clé + horloge synchronisée (rejet si dérive > 60 s).
- **Isolement multi-tenant** : middleware `TenantContextService` + `RowLevelSecurity` sur les querysets sensibles.

---

## 12. Roadmap d'implémentation suggérée

| Sprint | Périmètre |
|---|---|
| **S1** | `core`, `accounts`, `sites` — fondations & RBAC |
| **S2** | `devices`, `employees` — émission badges NFC, segment EMPLOYÉS de bout en bout |
| **S3** | `access_control`, `attendance` (basique) — scans NFC, pointages, dashboard temps réel |
| **S4** | `ouvriers`, appairage badge/casque — segment OUVRIERS, scénario UHF |
| **S5** | `antifraud` — règles UHF + BLE, alertes |
| **S6** | `visitors` (OCR + self-service QR) |
| **S7** | `notifications`, `mobile_sync` — multicanal & offline |
| **S8** | `reports`, `audit`, IA assistant — pilotage & finitions |

---

*Document maintenu par l'équipe Datarium / KAYDAN Groupe — version initiale 2026-04-30.*
