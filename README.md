# CAMTEL Budget App v5 — Guide de déploiement & utilisation

## Nouveautés v5
- Tableau Excel coloré : colonnes color-codées (violet=date, cyan=direction, bleu=imputation)
- Saisie inline : cliquez + Nouvelle ligne -> ligne s'ajoute dans le tableau comme Excel
- Logo CAMTEL : affiché dans le header design "C" bleu cyan
- Filtrage direction : sélectionner direction charge ses lignes budgétaires uniquement
- Montants formatés : 27 311 774 252 FCFA (espaces)
- DEPASSEMENT en rouge : fond rose/rouge comme Excel
- Import CSV corrigé : accepte votre format exact (CODE/REF NUMBER, DATE DE RECEPTION...)
- Fiche DCF : 2 fiches par page A4, Avis de la DCF, DISPONIBLE OUI/NON coches

## Deploiement Render - Remplacer main.py dans GitHub

Variables d'environnement:
  SECRET_KEY  = cle aleatoire
  ADMIN_USER  = admin
  ADMIN_PASS  = votre_mot_de_passe
  DB_PATH     = /data/camtel.db  (avec disque persistant)

## Premier demarrage - etapes obligatoires

### Etape 1 : Importer les lignes budgetaires
1. Aller dans Import/Export
2. Section Importer lignes budgetaires
3. Telecharger template_budget_lines_import.csv
4. Remplir avec vos imputations comptables par direction
5. Cliquer Importer lignes budget

SANS les lignes budgetaires importees, le tableau de bord reste a zero.

### Etape 2 : Importer les transactions historiques
1. Section Importer transactions
2. Telecharger template_transactions_import.csv
3. Copier vos donnees depuis DATA_ENTRY_TABLE_2025.csv
4. Saisir l'annee : 2025
5. Cliquer Importer

Colonnes acceptees:
DATE DE RECEPTION | CODE /REF NUMBER | DIRECTION | IMPUTATION COMPTABLE | 
NATURE (DEPENSE COURANTE...) | INTITULE DE LA COMMANDE | MONTANT | STATUT BUDGET

### Etape 3 : Creer les utilisateurs
1. Aller dans Utilisateurs
2. Ajouter utilisateur : nom, identifiant, mot de passe, role, directions

## Utilisation quotidienne

### Saisir une nouvelle transaction
1. Onglet Transactions
2. Cliquer + Nouvelle ligne -> ligne s'ajoute dans le tableau
3. Selectionner Direction -> lignes budgetaires de cette direction s'affichent
4. Selectionner Ligne budgetaire -> solde disponible s'affiche
5. Saisir date, montant, intitule
6. Cliquer Enregistrer

### Imprimer une fiche officielle DCF
1. Cocher 1 ou 2 transactions
2. Cliquer Imprimer selection -> 2 fiches par page A4

## Roles et permissions
admin, dcf_dir, dcf_sub : acces total + rapports + utilisateurs
agent : saisie sur ses directions uniquement
viewer : lecture seule
