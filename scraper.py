import csv
import hashlib
import json
import os
from datetime import datetime
from typing import List, Optional

import inquirer
import openai
import requests
from loguru import logger
from pydantic import BaseModel

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"
NATURE_JURIDIQUE = "5499,5410,5710"  # SARL, SAS
PER_PAGE = 25
FILTRE_QUALITE = [
    "Liquidateur",
    "Commissaire aux comptes titulaire",
    "Commissaire aux comptes suppléant",
]

SYSTEM_PROMPT = """
Met a jour ma liste de noms et indique si ils sont d'origine turque ou non.
Certains noms peuvent avoir des prenoms Francais apres naturalisation
"""

client = openai.Client(api_key=os.getenv("OPENAI_API_KEY"))


def get_companies(naf, nature_juridique, postal_code=None, departement=None, page=1):
    params = {
        "activite_principale": naf,
        "code_postal": postal_code,
        "departement": departement,
        "etat_administratif": "A",
        "nature_juridique": nature_juridique,
        "per_page": PER_PAGE,
        "page": page,
    }
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        return {"results": [], "error": str(e)}


def format_results(companies):
    formatted = []
    for company in companies.get("results", []):
        formatted.append(
            {
                "siren": company.get("siren"),
                "nom_complet": company.get("nom_complet"),
                "nom_raison_sociale": company.get("nom_raison_sociale"),
                "activite_principale": company.get("activite_principale"),
                "dirigeants": company.get("dirigeants", []),
                "adresse": company.get("siege", {}).get("adresse", ""),
                "code_postal": company.get("siege", {}).get("code_postal", ""),
                "libelle_commune": company.get("siege", {}).get("libelle_commune", ""),
                "date_creation": company.get("date_creation"),
                "nature_juridique": company.get("nature_juridique"),
            }
        )
    return formatted


def get_companies_listing(
    naf: str,
    postal_code: Optional[str] = None,
    departement: Optional[str] = None,
    allow_entrepreneur_individuel: bool = False,
) -> list:
    logger.info(
        f"Searching for companies with NAF: {naf}, postal_code: {postal_code}, departement: {departement}"
    )
    type_entreprises = (
        NATURE_JURIDIQUE + ",1000"
        if allow_entrepreneur_individuel
        else NATURE_JURIDIQUE
    )
    try:
        # Fetch first page
        data = get_companies(naf, type_entreprises, postal_code, departement, page=1)
        total_pages = data.get("total_pages", 1)
        all_results = format_results(data)

        # Fetch additional pages if needed
        if total_pages > 1:
            for page_num in range(2, total_pages + 1):
                logger.debug(f"Fetching page {page_num} of {total_pages}")
                page_data = get_companies(
                    naf, type_entreprises, postal_code, departement, page=page_num
                )
                all_results.extend(format_results(page_data))

        logger.info(
            f"Returning {len(all_results)} companies across {total_pages} pages"
        )
        return {
            "results_count": len(all_results),
            "results": all_results,
        }
    except Exception as e:
        logger.error(f"Error in get_companies_listing: {e}")
        return [{"error": str(e)}]


class OrigineTurc(BaseModel):
    id: str
    origine_turque: bool


class OrigineTurcResponse(BaseModel):
    results: List[OrigineTurc]


def identify_turkish_names(names) -> List[OrigineTurc]:
    logger.info(f"Identifying Turkish names for {len(names)} individuals")
    names_string = json.dumps(names)
    response = client.responses.parse(
        model="gpt-5-mini",
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": names_string,
            },
        ],
        text_format=OrigineTurcResponse,
    )
    logger.debug(f"Consumed {response.usage.total_tokens} tokens")
    return response.output_parsed.results


def results_cleanup_and_enrich(companies, check_turkish_names=False):
    cleaned = []
    all_dirigeants = []
    for company in companies:
        if "error" in company:
            cleaned.append(company)
            continue
        dirigeants = [
            d
            for d in company.get("dirigeants", [])
            if d.get("type_dirigeant") == "personne physique"
            and d.get("qualite") not in FILTRE_QUALITE
        ]
        for dirigeant in dirigeants:
            unique_str = f"{dirigeant.get('nom', '')}{dirigeant.get('prenoms', '')}"
            dirigeant["id"] = hashlib.md5(unique_str.encode("utf-8")).hexdigest()[:8]
            all_dirigeants.append(
                {
                    "id": dirigeant["id"],
                    "nom": dirigeant.get("nom", ""),
                    "prenoms": dirigeant.get("prenoms", ""),
                }
            )
        company["dirigeants"] = dirigeants
        cleaned.append(company)

    if check_turkish_names:
        try:
            if not all_dirigeants:
                logger.info("No dirigeants found to check for Turkish names.")
                return cleaned
            turkish_origins = identify_turkish_names(all_dirigeants)
            for company in cleaned:
                for dirigeant in company.get("dirigeants", []):
                    match = next(
                        (
                            item
                            for item in turkish_origins
                            if item.id == dirigeant["id"]
                        ),
                        None,
                    )
                    if match:
                        dirigeant["origine_turque"] = match.origine_turque
                    else:
                        dirigeant["origine_turque"] = False
        except Exception as e:
            logger.error(f"Error identifying Turkish names: {e}")
    return cleaned


def write_csv(companies, filename="companies.csv"):
    headers = [
        "dirigeant_nom",
        "dirigeant_prenoms",
        "dirigeant_date_de_naissance",
        "dirigeant_qualite",
        "dirigeant_origine_turque",
        "dirigeant_nationalite",
        "siren",
        "nom_complet",
        "activite_principale",
        "adresse",
        "code_postal",
        "libelle_commune",
        "date_creation",
        "nature_juridique",
    ]

    # Ensure the directory "data_output" exists
    os.makedirs("data_output", exist_ok=True)

    # Open the CSV file for writing
    with open(os.path.join("data_output", filename), "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()

        # Iterate over each company in results
        for company in companies:
            # Get company fields, handling None
            company_data = {
                "siren": company.get("siren", ""),
                "nom_complet": company.get("nom_complet", ""),
                "activite_principale": company.get("activite_principale", ""),
                "adresse": company.get("adresse", ""),
                "code_postal": company.get("code_postal", ""),
                "libelle_commune": company.get("libelle_commune", ""),
                "date_creation": company.get("date_creation", ""),
                "nature_juridique": company.get("nature_juridique", ""),
            }

            # Iterate over each director in the company
            for dirigeant in company.get("dirigeants", []):
                # Get director fields, handling None
                dirigeant_data = {
                    "dirigeant_nom": dirigeant.get("nom", ""),
                    "dirigeant_prenoms": dirigeant.get("prenoms", ""),
                    "dirigeant_date_de_naissance": dirigeant.get(
                        "date_de_naissance", ""
                    ),
                    "dirigeant_qualite": dirigeant.get("qualite", ""),
                    "dirigeant_origine_turque": dirigeant.get("origine_turque", False),
                }

                # Combine company and director data
                row = {**dirigeant_data, **company_data}
                writer.writerow(row)
    logger.info(f"CSV file '{filename}' written successfully.")


if __name__ == "__main__":
    questions = [
        inquirer.Text("naf", message="Enter NAF code (e.g., 43.99A)"),
        inquirer.Text("departement", message="Enter departement code (e.g., 75)"),
        inquirer.Confirm(
            "allow_entrepreneur_individuel",
            message="Include Entrepreneur Individuel?",
            default=False,
        ),
        inquirer.Confirm(
            "check_turkish_names",
            message="Check for Turkish names? (requires OPENAI_API_KEY)",
            default=False,
        ),
    ]
    answers = inquirer.prompt(questions)
    naf = answers["naf"]
    departement = answers["departement"]
    data = get_companies_listing(
        naf,
        departement=departement,
        allow_entrepreneur_individuel=answers["allow_entrepreneur_individuel"],
    )
    cleaned_data = results_cleanup_and_enrich(
        data["results"], check_turkish_names=answers["check_turkish_names"]
    )
    output_filename = f"companies_{naf}_{departement}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    write_csv(cleaned_data, filename=output_filename)
