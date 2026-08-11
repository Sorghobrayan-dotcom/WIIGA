"""Transformer les mesures en tableaux Markdown, et rien d'autre.

Ce fichier n'a le droit de calculer aucun chiffre. Il lit `comparaison.json` et
`transfert.json`, et les met en forme. C'est délibéré : dès qu'un chiffre est
recopié à la main dans un README, il survit à la mesure qui l'a produit et on
finit par défendre en public un résultat qui n'existe plus dans le code.

Les deux commandes qui produisent les JSON sont les seules sources :

    python -m wiiga.resultats --journees 365
    python -m wiiga.transfert  --journees 365

Puis `python -m wiiga.rapport` réécrit la section chiffrée du README entre les
deux balises. Le reste du README est écrit à la main et n'est jamais touché.
"""

from __future__ import annotations

import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
COMPARAISON = RACINE / "resultats" / "comparaison.json"
TRANSFERT = RACINE / "resultats" / "transfert.json"
README = RACINE / "README.md"

DEBUT = "<!-- chiffres:début -->"
FIN = "<!-- chiffres:fin -->"

SAISONS = ("sèche chaude", "pluies", "sèche tempérée")


def _fr(x: float, decimales: int = 0) -> str:
    """Un nombre lisible : espace fine pour les milliers, virgule décimale."""
    s = f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return s


def tableau_principal(d: dict) -> list[str]:
    m = d["mesures"]
    lignes = [
        "| politique | heures à sec / jour | jours à sec / 200 | FCFA / jour "
        "| L gasoil / jour | kg CO₂ / jour | creux moyen |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for nom, v in m.items():
        gras = "**" if nom.startswith("agent WIIGA (") else ""
        lignes.append(
            f"| {gras}{nom}{gras} | {_fr(v['heures_a_sec_par_jour'], 2)} "
            f"| {v['jours_avec_coupure_sur_200']} | {_fr(v['fcfa_par_jour'])} "
            f"| {_fr(v['litres_gasoil_par_jour'], 1)} "
            f"| {_fr(v['kg_co2_par_jour'], 1)} | {_fr(v['creux_moyen'], 2)} |"
        )
    return lignes


def tableau_saisons(d: dict) -> list[str]:
    m = d["mesures"]
    presentes = [s for s in SAISONS if s in next(iter(m.values()))["heures_a_sec_par_saison"]]
    lignes = [
        "| politique | " + " | ".join(presentes) + " |",
        "|---" * (len(presentes) + 1) + "|",
    ]
    for nom, v in m.items():
        gras = "**" if nom.startswith("agent WIIGA (") else ""
        cases = " | ".join(
            _fr(v["heures_a_sec_par_saison"][s], 2) for s in presentes
        )
        lignes.append(f"| {gras}{nom}{gras} | {cases} |")
    return lignes


def tableau_parole(d: dict) -> list[str]:
    m = d["mesures"]
    lignes = [
        "| politique | alertes / jour | justesse | confiance finale |",
        "|---|---:|---:|---:|",
    ]
    for nom, v in m.items():
        if v["alertes_par_jour"] == 0 and not nom.startswith("agent"):
            continue
        lignes.append(
            f"| {nom} | {_fr(v['alertes_par_jour'], 2)} "
            f"| {_fr(v['justesse_alertes'] * 100)} % "
            f"| {_fr(v['confiance_finale'], 2)} |"
        )
    return lignes


def tableau_transfert(d: dict) -> list[str]:
    lignes = [
        "| ville | pluies / chaude / tempérée (jours) | agent | règle écrite "
        "| écart | alertes / jour |",
        "|---|:--:|---:|---:|---:|---:|",
    ]
    for nom, v in d["villes"].items():
        s = v["saisons"]
        saisons = " / ".join(
            str(s.get(k, 0)) for k in ("pluies", "sèche chaude", "sèche tempérée")
        )
        vu = " *(entraînement)*" if nom == d["entraine_sur"] else ""
        lignes.append(
            f"| {nom}{vu} | {saisons} "
            f"| {_fr(v['agent']['heures_a_sec_par_jour'], 2)} "
            f"| {_fr(v['regle_ecrite']['heures_a_sec_par_jour'], 2)} "
            f"| {_fr(v['ecart_heures_a_sec_pct'])} % "
            f"| {_fr(v['agent']['alertes_par_jour'], 2)} |"
        )
    return lignes


def construire() -> str:
    d = json.loads(COMPARAISON.read_text(encoding="utf-8"))
    r = d["resume"]
    bloc: list[str] = []

    bloc.append(
        f"*{d['journees']} journées, une par jour de l'année, graines identiques "
        f"pour toutes les politiques. Mesuré le {d['genere_le'][:10]}, "
        f"régénérable par `python -m wiiga.resultats --journees {d['journees']}`.*"
    )
    bloc += ["", "### Ce que chaque politique coûte à la ville", ""]
    bloc += tableau_principal(d)

    bloc += ["", "### Le même tableau, saison par saison — heures à sec / jour", ""]
    bloc += tableau_saisons(d)
    bloc += [
        "",
        "La moyenne annuelle cache l'essentiel : c'est en saison sèche chaude que",
        "les règles écrites lâchent, et c'est là que la ville a le plus soif.",
    ]

    bloc += ["", "### La parole : ce que l'agent dit à la ville, et si on le croit", ""]
    bloc += tableau_parole(d)

    ecarts = [
        ("la pratique actuelle", r["vs_pratique_actuelle"]),
        ("la règle écrite à la main", r["vs_regle_ecrite"]),
        ("lui-même, privé de parole", r["vs_lui_meme_sans_la_parole"]),
    ]
    bloc += ["", "### En un coup d'œil", ""]
    for titre, e in ecarts:
        morceaux = [f"{_fr(e['heures_a_sec_pct'])} % d'heures à sec en moins"]
        if "cout_pct" in e:
            morceaux.append(f"{_fr(e['cout_pct'])} % moins cher")
        if "co2_pct" in e:
            morceaux.append(f"{_fr(e['co2_pct'])} % de CO₂ en moins")
        bloc.append(f"- **contre {titre}** : " + ", ".join(morceaux))

    if TRANSFERT.exists():
        t = json.loads(TRANSFERT.read_text(encoding="utf-8"))
        bloc += [
            "",
            "### Et dans une ville qu'il n'a jamais vue",
            "",
            f"*Les poids entraînés sur {t['entraine_sur']}, rejoués tels quels. "
            "Rien n'est réentraîné : on remplace la climatologie, c'est tout.*",
            "",
        ]
        bloc += tableau_transfert(t)
        if t["tient_partout"]:
            bloc += [
                "",
                "L'agent bat la règle écrite dans **toutes** ces villes, y compris "
                "dans l'hémisphère sud où les saisons sont inversées.",
            ]

    return "\n".join(bloc)


def main() -> None:
    bloc = construire()
    if not README.exists():
        print(bloc)
        raise SystemExit(
            f"\n({README.name} n'existe pas encore — bloc affiché plutôt qu'inséré)"
        )

    texte = README.read_text(encoding="utf-8")
    if DEBUT not in texte or FIN not in texte:
        print(bloc)
        raise SystemExit(f"\n(balises {DEBUT} / {FIN} absentes du README)")

    avant = texte.split(DEBUT)[0]
    apres = texte.split(FIN)[1]
    README.write_text(f"{avant}{DEBUT}\n\n{bloc}\n\n{FIN}{apres}", encoding="utf-8")
    print(f"section chiffrée réécrite dans {README.name}")


if __name__ == "__main__":
    main()
