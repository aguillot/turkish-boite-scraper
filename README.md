# Turkish Boite Scraper

Scraper interactif pour récupérer des entreprises françaises par code NAF et
departement, avec option d’identification des noms d’origine turque.

## Prérequis

- Python 3.12 (voir `.python-version`)
- Accès internet (API `recherche-entreprises.api.gouv.fr`)
- *(Optionnel)* Clé OpenAI pour l’identification des noms d’origine turque

## Installation

Avec `uv` (recommandé) :

```bash
uv sync
```

Ou avec `pip` :

```bash
pip install -e .
```

## Configuration

Pour activer l’analyse des noms turcs, définir la variable d’environnement :

```bash
export OPENAI_API_KEY="votre_cle"
```

## Exemples d’exécution

Lancer le scraper interactif :

```bash
python scraper.py
```

Exemple de réponses :

```
Select NAF code: 56.10A - Restaurants et services de restauration mobile
Enter departement code (e.g., 75): 75
Include Entrepreneur Individuel? [y/N]: n
Check for Turkish names? (requires OPENAI_API_KEY) [y/N]: y
Filter companies created before 2024? [Y/n]: y
```

Le fichier CSV est généré dans `data_output/` avec un nom du type :

```
YYYYMMDDHHMMSS_companies_{NAF}_{DEPARTEMENT}.csv
```
