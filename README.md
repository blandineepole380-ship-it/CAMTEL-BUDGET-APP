# CAMTEL Budget App v4 — Guide de déploiement

## Nouveautés v4 (vs v3)
- ✅ Lignes budgétaires par direction avec imputation comptable complète
- ✅ 46 directions CAMTEL préconfigurées (BUM, BUT, BUF, DG, DRH, DICOM, DIRCAB...)
- ✅ Fiche DCF officielle: DISPONIBLE OUI✓/NON✓, montants formatés (300 000 000 FCFA)
- ✅ 2 fiches par page A4, sélection multiple pour impression batch
- ✅ Multi-utilisateurs: Admin, Directeur DCF, Sous-Dir. Budget, Agent, Observateur
- ✅ Accès par direction: chaque agent voit uniquement ses directions assignées
- ✅ Import/Export CSV: transactions historiques + budgets annuels (2026, 2027...)
- ✅ Rapports mensuels téléchargeables
- ✅ Avis de la DCF (remplacé SAAF)

## Déploiement sur Render

### Fichiers requis dans votre repo GitHub:
- `main.py` — Application complète
- `requirements.txt` — Dépendances Python
- `Dockerfile` — Configuration Docker

### Variables d'environnement:
| Variable | Description | Défaut |
|---|---|---|
| `SECRET_KEY` | Clé secrète sessions (changer!) | `change-me` |
| `ADMIN_USER` | Identifiant admin | `admin` |
| `ADMIN_PASS` | Mot de passe admin | `admin123` |
| `DB_PATH` | Chemin SQLite | `camtel.db` |
| `FRONTEND_ORIGIN` | URL Lovable (CORS) | `*` |

### Données persistantes (IMPORTANT sur Render):
1. Render → votre service → **Disks** → Add disk
2. Mount path: `/data`
3. Définir `DB_PATH=/data/camtel.db`

## Premier démarrage
1. Connectez-vous: `admin` / `admin123`
2. Allez dans **⬆ Import/Export** → importez vos lignes budgétaires CSV
3. Ou dans **Lignes Budget** → créez les lignes manuellement
4. Dans **👥 Utilisateurs** → créez les comptes de vos agents
5. Assignez les directions à chaque agent

## Import du budget annuel (2026, 2027...)
1. Télécharger `template_budget_lines_import.csv`
2. Remplir avec les lignes du nouveau budget
3. Importer via **⬆ Import/Export** → "Importer des lignes budgétaires"

## Import de transactions historiques
1. Télécharger `template_transactions_import.csv`
2. Remplir avec vos transactions passées
3. Importer via **⬆ Import/Export** → "Importer des transactions"

## Rôles et accès
| Rôle | Transactions | Lignes Budget | Utilisateurs | Rapports |
|---|---|---|---|---|
| admin | ✅ Total | ✅ Total | ✅ | ✅ |
| dcf_dir | ✅ Total | ✅ Total | ✅ | ✅ |
| dcf_sub | ✅ Total | ✅ Total | ✅ | ✅ |
| agent | ✅ Ses directions | 👁 Lecture | ✗ | 👁 Lecture |
| viewer | 👁 Lecture | 👁 Lecture | ✗ | 👁 Lecture |

## API pour Lovable Frontend
```
POST /api/login/token   → Bearer token
GET  /api/transactions?year=&direction=&q=
POST /api/transactions
GET  /api/budget-lines?year=&direction=
GET  /api/dashboard?year=
GET  /api/export/transactions?year=
```

## Fiche d'engagement
- Cliquez 🖨 sur une transaction → fiche officielle format CAMTEL
- Cochez plusieurs transactions → "Imprimer sélection" → 2 fiches par page A4
- Format: DISPONIBLE OUI ✓ ou NON ✓, montants "300 000 000 FCFA", Avis de la DCF
