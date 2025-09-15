import pandas as pd
from loguru import logger

NAF_N5_FILE = "naf2008_liste_n5.xls"


def get_inquirer_formatted_naf_codes():
    try:
        df = pd.read_excel(NAF_N5_FILE)
        df = df[df["include"] == "o"]

        logger.info(f"Loaded {len(df)} NAF codes")

        code_naf_actifs = df.to_dict(orient="records")
        result = {item["Code"]: item["Libellé"] for item in code_naf_actifs}
    except Exception as e:
        logger.error(f"Error loading NAF codes: {e}")
        result = {"62.01Z": "Programmation informatique"}

    return [(f"{desc} ({code})", code) for code, desc in result.items()]
