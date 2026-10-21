# Modele de Scoring (PD) et calcul des ECL

Ce projet est une simulation complète d'un scoring de risque de crédit selon la norme IFRS 9. Un pipeline ETL alimente une base **PostgreSQL** en couches, entraîne un modèle de **Probabilité de Défaut (PD)**, calcule l'**Expected Credit Loss (ECL)** de tout le portefeuille, et une **API FastAPI** expose ces résultats à un dashboard **Streamlit**.

![Aperçu du Dashboard](scoring_app.png)

## Architecture

Quatre services, chacun dans son conteneur (`docker-compose.yml`) :

```
                    ┌────────────────────────── PostgreSQL (db) ──────────────────────────┐
 data_final.csv ──► │ raw.loans ──► staging.loans ──► mart.pd_scores / mart.ecl_results   │
        (etl)       │                     │              mart.model_runs    ops.etl_runs  │
                    └─────────────────────┼───────────────────────▲──────────────────────┘
                                          ▼                       │ lecture
                              data/models/pd_<id>.pkl ──────► api (FastAPI :8000) ◄── web (Streamlit :8501)
```

| Service | Rôle | Code |
| :--- | :--- | :--- |
| `db` | Stockage, en couches (voir ci-dessous) | `migrations/` (schémas versionnés par Alembic) |
| `etl` | Job à la demande : ingestion, nettoyage/imputation, entraînement, scoring | `pkg/` |
| `api` | Scoring à la volée, portefeuille, historique des exécutions | `services/api/` |
| `web` | Dashboard. Ne parle **qu'à l'API**, jamais à la base | `web/` |

Toute la logique métier vit dans `pkg/` : l'API et l'ETL ne font que l'appeler. Le front peut
être remplacé (React prévu) sans toucher au reste, puisqu'il ne dépend que des contrats de l'API.

### Couches de données (schémas PostgreSQL)

| Schéma | Contenu | Tables |
| :--- | :--- | :--- |
| `raw` | Données telles que reçues de la source, sans contrainte | `loans` |
| `staging` | Données nettoyées et imputées, split train/test, modalités contrôlées (`CHECK`) | `loans` |
| `mart` | Résultats métier lus par l'API | `model_runs`, `pd_scores`, `ecl_results` |
| `ops` | Traçabilité : chaque exécution de l'ETL (statut, durée, lignes lues/écrites, erreur) | `etl_runs`, `alembic_version` |

Chaque ligne de `raw` et `staging` porte l'id de l'exécution ETL qui l'a écrite, et chaque score
l'id du modèle qui l'a produit : on peut toujours remonter à l'origine d'un chiffre.

### Choix de calcul de l'ECL

* **PD** : régression logistique (`scikit-learn`) ; un seul modèle PD est actif à la fois.
* **LGD** : hypothèse fixe de 45 % (prêt non garanti), paramétrable (`SCORING_DEFAULT_LGD`).
* **EAD** : tous les prêts des données sont soldés (`out_prncp = 0`), l'EAD retenue est donc le
  **capital à l'octroi**, reconstruit exactement depuis la mensualité, le taux et la durée
  (formule d'annuité).
* **Stade** : l'ECL est calculé à l'octroi, donc en **stade 1**.

## Structure du Projet

```
scoring_ifrs9/
├── pkg/                         # Package métier, importé sous le nom `src`
│   ├── src/
│   │   ├── config.py            # Paramètres (variables d'env SCORING_* ou .env)
│   │   ├── features.py          # Cible, features du modèle, modalités, variables d'imputation
│   │   ├── etl/                 # extract, transform (split, imputations), pipeline, runs (traçabilité)
│   │   ├── modeling/            # train (pipeline PD), registry, pipeline (entraînement + activation)
│   │   ├── ifrs9/               # ead (capital à l'octroi), ecl (ECL = PD × LGD × EAD)
│   │   ├── db/                  # Tables SQLAlchemy, sessions, COPY en masse, requêtes de lecture
│   │   └── cli.py               # Commande `scoring-ifrs9`
│   └── tests/
├── services/api/                # API FastAPI (app/main.py, routers/, schemas.py) et ses tests
├── web/                         # Dashboard Streamlit : simulateur, portefeuille, modèles & ETL
├── migrations/                  # Migrations Alembic
├── Dockerfile                   # Une cible par service : etl, api, web
├── docker-compose.yml
├── conftest.py                  # Fixtures de test partagées
├── data/processed/              # Anciens jeux imputés (servent à reconstruire la source)
└── notebooks/                   # Exploration
```

---

## Lancement avec Docker (recommandé)

Prérequis : [Docker Desktop](https://www.docker.com/products/docker-desktop/) et [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
cp .env.example .env
uv run scoring-ifrs9 rebuild-source      # 1re fois : recrée data/raw/data_final.csv (voir « Source »)
docker compose up -d --build             # db + migrations + api + web
docker compose run --rm etl              # pipeline complet (~3-4 min pour 1,35 M de prêts)
```

* Dashboard : http://localhost:8501
* API et sa documentation interactive : http://localhost:8000/docs

## Lancement local sans Docker ni droits administrateur (Windows)

Sur un poste où Docker ne peut pas être installé, `scripts/local_stack.py` installe un
PostgreSQL portable (binaires officiels EDB) dans `%LOCALAPPDATA%\scoring-postgres`, puis lance
l'API et le Streamlit en arrière-plan. La connexion est lue dans `SCORING_DATABASE_URL` (`.env`).

```bash
cp .env.example .env
uv run python scripts/local_stack.py setup    # 1re fois : Postgres, bases, migrations, pipeline complet
uv run python scripts/local_stack.py start    # Postgres + API (:8000) + Streamlit (:8501)
uv run python scripts/local_stack.py stop
uv run python scripts/local_stack.py status
```

Les logs de l'API et du Streamlit sont dans `%LOCALAPPDATA%\scoring-postgres\logs\`.

## Lancement en local (développement)

```bash
uv sync                                  # installe tous les services dans .venv
cp .env.example .env
docker compose up -d db                  # seulement Postgres
uv run alembic upgrade head              # crée les schémas et les tables
uv run scoring-ifrs9 rebuild-source      # 1re fois uniquement
uv run scoring-ifrs9 run-all             # ingest -> staging -> train -> score

uv run uvicorn app.main:app --reload     # API sur http://localhost:8000
uv run streamlit run web/streamlit_app.py
```

### Commandes de l'ETL

| Commande | Effet |
| :--- | :--- |
| `scoring-ifrs9 rebuild-source` | Anciens parquets -> `data/raw/data_final.csv` |
| `scoring-ifrs9 ingest` | Fichier source -> `raw.loans` (recharge complète, vide aussi staging et mart) |
| `scoring-ifrs9 staging` | `raw.loans` -> `staging.loans` (split, imputations, contrôles) |
| `scoring-ifrs9 train` | Entraîne le modèle PD, l'enregistre dans `mart.model_runs` et l'active |
| `scoring-ifrs9 score` | PD, EAD, ECL de tous les prêts avec le modèle actif -> `mart` |
| `scoring-ifrs9 run-all` | Les quatre étapes ci-dessus |

Chaque étape s'exécute dans une transaction : en cas d'erreur, la table cible garde son contenu
précédent et l'échec est enregistré dans `ops.etl_runs`.

### API

| Méthode | Route | Rôle |
| :--- | :--- | :--- |
| `POST` | `/score` | PD et ECL d'un prêt (EAD et LGD optionnelles) |
| `GET` | `/portfolio/summary` | Agrégats global et par grade (PD moyenne, défaut observé, EAD, ECL) |
| `GET` | `/loans`, `/loans/{id}` | Prêts paginés et filtrables, avec leur résultat ECL |
| `GET` | `/model-runs`, `/etl-runs` | Historique des modèles et des exécutions |
| `GET` | `/reference` | Valeurs autorisées (grades, durées...) pour les formulaires |
| `GET` | `/health` | État de l'API et de la base |

### Modifier un schéma de base

Éditer `pkg/src/db/models.py`, puis `uv run alembic revision --autogenerate -m "description"`,
relire le fichier généré dans `migrations/versions/`, et `uv run alembic upgrade head`.

### Tests

```bash
uv run pytest                            # tests sans base (les tests PostgreSQL sont ignorés)

# Avec une base de test vide et jetable (créée une fois : CREATE DATABASE scoring_test)
SCORING_TEST_DATABASE_URL=postgresql+psycopg://scoring:scoring@localhost:5432/scoring_test uv run pytest
```

---

## Données et Sélection des Variables

Ce projet utilise un jeu de données de prêts Lending Club pour modéliser le risque de défaut. Les variables clés utilisées pour l'entraînement du modèle (les *features*) sont les suivantes :

### Features d'Entrée (Inputs)

| Variable | Définition |
| :--- | :--- |
| `term` | Nombre de paiements du prêt (36 ou 60 mois). |
| `int_rate` | Taux d'intérêt sur le prêt. |
| `installment` | Paiement mensuel estimé. |
| `grade` | Note de prêt attribuée par Lending Club. |
| `emp_length` | Ancienneté professionnelle (ex: '2 years', '10+ years'). |
| `home_ownership` | Statut de propriété du logement (ex: RENT, OWN, MORTGAGE). |
| `annual_inc` | Revenu annuel déclaré par l'emprunteur. |
| `dti` | Taux d'endettement (remboursements / revenu mensuel). |
| `tot_cur_bal` | Somme de tous les soldes impayés. |
| `open_acc_6m` | Nombre de comptes de crédit ouverts (6 derniers mois). |
| `total_bal_il` | Total des montants impayés restants. |
| `inq_fi` | Nombre de demandes de crédit (6 derniers mois). |
| `mort_acc` | Nombre de comptes hypothécaires actifs. |
| `num_sats` | Nombre de crédits jugés satisfaisants (sans retard). |

### Cible et Variables Exclues (Leakage)

Les variables suivantes sont des **résultats** du prêt et ne sont **pas** utilisées comme *features* pour entraîner le modèle de PD, afin d'éviter les fuites de données :

> * **`loan_status` (Cible Y) :** Statut du prêt (ex: Défaut / Payé). C'est la variable que nous cherchons à prédire.
> * **`out_prncp` :** Principal restant dû (nul dans les données : tous les prêts sont soldés).
> * **`total_pymnt` :** Total des paiements reçus.
> * **`recoveries` :** Montants récupérés après mise en défaut (utiles pour un futur modèle de LGD).

### Source

Le fichier brut d'origine (`data_final.csv`) n'est plus disponible. `scoring-ifrs9 rebuild-source`
le reconstruit à partir des jeux train/test conservés dans `data/processed/` (1 345 310 prêts) :
la structure est identique, mais ces données sont **déjà imputées** (aucune valeur manquante).
Avec un nouveau fichier brut au même format, seule cette étape change.

Les définitions complètes des variables ont été identifiées à partir de [cette référence RStudio](https://rstudio-pubs-static.s3.amazonaws.com/290261_676d9bb194ae4c9882f599e7c0a808f2.html).
