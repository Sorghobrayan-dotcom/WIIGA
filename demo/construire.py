"""Construire la page de démonstration, chiffres compris.

La page est **entièrement autonome** : les données sont écrites à l'intérieur du
HTML au moment de la construction. Aucune requête réseau, aucun serveur, aucune
fonction *serverless*. Elle s'ouvre depuis un disque comme depuis GitHub Pages,
et elle ne peut pas tomber en panne devant un jury parce qu'une API a changé
d'avis — c'est exactement le piège qui a coûté un concours précédent.

Elle ne calcule aucun résultat non plus. Elle lit les JSON de `resultats/`,
demande à `scenarios.py` les journées rejouables, et met en forme. Si un chiffre
de la page est faux, c'est que la mesure est fausse, et on la corrige à la
source plutôt qu'ici.

Construction : `python demo/construire.py`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(ICI))

RESULTATS = RACINE / "resultats"
#: GitHub Pages ne sait servir que la racine du dépôt ou `/docs`, jamais un
#: dossier arbitraire. La page se construit donc directement là où elle sera
#: publiée, plutôt que d'être recopiée à la main la veille du dépôt.
SORTIE = RACINE / "docs" / "index.html"

def rassembler() -> dict:
    """Tout ce que la page dessine, en un seul objet.

    `comparaison` est obligatoire : sans elle il n'y a pas de page. Les trois
    autres sont facultatives, et la page se replie proprement si l'une manque —
    on préfère une section absente à une section qui affiche des zéros.
    """
    from scenarios import construire as construire_scenarios

    donnees = {
        "comparaison": json.loads((RESULTATS / "comparaison.json").read_text(encoding="utf-8")),
        "scenarios": construire_scenarios(),
    }
    for cle, fichier in (
        ("transfert", "transfert.json"),
        ("equivalence", "equivalence.json"),
        ("graines", "graines.json"),
    ):
        chemin = RESULTATS / fichier
        if chemin.exists():
            donnees[cle] = json.loads(chemin.read_text(encoding="utf-8"))
        else:
            print(f"  (absent : {fichier} — la section correspondante sera masquée)")
    return donnees


def main() -> None:
    gabarit = (ICI / "gabarit.html").read_text(encoding="utf-8")
    donnees = rassembler()
    charge = json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))

    marque = "/*DONNEES*/"
    if marque not in gabarit:
        raise SystemExit(f"marque {marque} absente de gabarit.html")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(gabarit.replace(marque, f"const DONNEES={charge};"), encoding="utf-8")
    poids = SORTIE.stat().st_size / 1024
    print(f"page écrite : {SORTIE}  ({poids:.0f} Ko, autonome)")
    c = donnees["comparaison"]["resume"]
    print(f"  contre la règle écrite : "
          f"{c['vs_regle_ecrite']['heures_a_sec_pct']:.0f} % d'heures à sec en moins")
    print(f"  {c['en_humain']['personnes_jours_epargnees_par_an_vs_regle']:,.0f} "
          f"personnes-jours par an")
    print(f"  {len(donnees['scenarios']['villes'])} villes jouables dans la console")


if __name__ == "__main__":
    main()
