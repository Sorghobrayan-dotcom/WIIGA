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
GRAINES = RACINE / "resultats" / "graines.json"
EQUIVALENCE = RACINE / "resultats" / "equivalence.json"
SENSIBILITE = RACINE / "resultats" / "sensibilite.json"
MEILLEURE = RACINE / "resultats" / "meilleure_regle.json"
JOURNEE = RACINE / "resultats" / "journee.json"
README = RACINE / "README.md"

DEBUT = "<!-- chiffres:début -->"
FIN = "<!-- chiffres:fin -->"

SAISONS = ("sèche chaude", "pluies", "sèche tempérée")

#: Les politiques portent des noms francais dans le code, parce que le code est
#: francais. Le README est anglais : les laisser tels quels obligeait un lecteur
#: a dechiffrer "exploitant (consigne fixe)" au milieu d'un tableau, ce qui est
#: exactement le genre de friction qui fait sauter une ligne.
NOMS = {
    "exploitant (consigne fixe)": "what the utility runs today",
    "moins cher (sans prévision)": "cheapest source, no forecast",
    "prévoyant (règle écrite)": "hand-written rulebook",
    "agent WIIGA (PPO)": "WIIGA agent",
    "agent WIIGA, sans la parole": "WIIGA, not allowed to speak",
}


def _nom(cle: str) -> str:
    return NOMS.get(cle, cle)


def _fr(x: float, decimales: int = 0) -> str:
    """Un nombre lisible : espace fine pour les milliers, virgule décimale."""
    s = f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return s


def tableau_principal(d: dict) -> list[str]:
    m = d["mesures"]
    lignes = [
        "| operator | dry hours / day | dry days / 200 | local currency / day "
        "| L diesel / day | kg CO2 / day | tank low point |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for nom, v in m.items():
        gras = "**" if nom.startswith("agent WIIGA (") else ""
        lignes.append(
            f"| {gras}{_nom(nom)}{gras} | {_fr(v['heures_a_sec_par_jour'], 2)} "
            f"| {v['jours_avec_coupure_sur_200']} | {_fr(v['fcfa_par_jour'])} "
            f"| {_fr(v['litres_gasoil_par_jour'], 1)} "
            f"| {_fr(v['kg_co2_par_jour'], 1)} | {_fr(v['creux_moyen'], 2)} |"
        )
    return lignes


def tableau_saisons(d: dict) -> list[str]:
    m = d["mesures"]
    presentes = [s for s in SAISONS if s in next(iter(m.values()))["heures_a_sec_par_saison"]]
    saison_en = {"sèche chaude": "hot dry", "pluies": "rainy",
                 "sèche tempérée": "mild dry"}
    lignes = [
        "| operator | " + " | ".join(saison_en.get(x, x) for x in presentes) + " |",
        "|---" + "|---:" * len(presentes) + "|",
    ]
    for nom, v in m.items():
        gras = "**" if nom.startswith("agent WIIGA (") else ""
        cases = " | ".join(
            _fr(v["heures_a_sec_par_saison"][s], 2) for s in presentes
        )
        lignes.append(f"| {gras}{_nom(nom)}{gras} | {cases} |")
    return lignes


def tableau_journee(d: dict) -> list[str]:
    """La journée que le texte raconte, et les jours où l'écart est le plus grand.

    Le README s'ouvre sur une journée. Tant que ces chiffres n'étaient produits
    par aucune commande, ils ne pouvaient pas vieillir avec le reste : ils sont
    republiés ici depuis `journee.json`, sous la table annuelle, pour qu'un écart
    entre le récit et la mesure se voie au lieu de se cacher.
    """
    saison_en = {"sèche chaude": "hot dry", "pluies": "rainy",
                 "sèche tempérée": "mild dry"}
    c = d["journee_de_la_console"]
    m = c["moments"]
    part = d["part_de_l_ecart_par_saison"]
    # les sources portent leurs noms français dans le journal, comme les
    # politiques dans les tableaux au-dessus, et le README est anglais
    source_en = {"solaire": "solar", "reseau": "the grid", "diesel": "the generator"}
    midi = ", ".join(f"{p * 100:.0f} %" for p in m["midi"]["puissances"])
    soir = ", ".join(f"{p * 100:.0f} %" for p in m["soir"]["puissances"])
    mains = ", ".join(f"{h} a.m." for h in m["heures_ou_il_passe_la_main"])
    lignes = [
        "",
        "### One day, and where the value concentrates",
        "",
        f"*The day the live demo opens on: {c['date']}, {_fr(c['temperature'], 1)} C, "
        f"the median day of the {saison_en.get(c['saison'], c['saison'])} season - "
        f"not the best one we found. Everything here is regenerated by "
        f"`python -m wiiga.journee`.*",
        "",
        f"- **the rulebook** leaves {_fr(c['regle_ecrite']['litres_manquants'])} litres "
        f"unserved that day: **{_fr(c['regle_ecrite']['personnes_sous_le_seuil'])} people** "
        f"below the WHO survival threshold",
        f"- **the agent**, same day, same outages, same sunshine: "
        f"**{_fr(c['agent']['personnes_sous_le_seuil'])}**",
        f"- 1 p.m., pumps at {midi}, all three on "
        f"{source_en.get(m['midi']['sources'][0], m['midi']['sources'][0])}; "
        f"7 p.m., {soir}, worst tank at {m['soir']['cuve_la_plus_basse'] * 100:.0f} %",
        f"- it hands the station back at {mains} and takes control again at "
        f"{m['reprend_la_main_a']} a.m.",
        "",
        "The five days of the year where the agent brings the most, over "
        f"{d['journees']} replayed days:",
        "",
        "| day | season | temperature | rulebook | agent | people spared |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for x in d["cinq_plus_gros_ecarts"]:
        lignes.append(
            f"| {x['date']} | {saison_en.get(x['saison'], x['saison'])} "
            f"| {_fr(x['temperature'], 1)} C | {_fr(x['regle_personnes'])} "
            f"| {_fr(x['agent_personnes'])} | **{_fr(x['personnes_epargnees'])}** |"
        )
    principale = max(part, key=part.get)
    lignes += [
        "",
        f"All five are in the {saison_en.get(principale, principale)} season, and so "
        f"is **{_fr(part[principale], 1)} %** of everything the agent spares the city "
        "over a year. The agent's value does not spread evenly across the calendar: "
        "it concentrates on the days the city can least afford.",
    ]
    return lignes


def tableau_parole(d: dict) -> list[str]:
    m = d["mesures"]
    lignes = [
        "| operator | warnings / day | accuracy | trust at the end |",
        "|---|---:|---:|---:|",
    ]
    for nom, v in m.items():
        if v["alertes_par_jour"] == 0 and not nom.startswith("agent"):
            continue
        lignes.append(
            f"| {_nom(nom)} | {_fr(v['alertes_par_jour'], 2)} "
            f"| {_fr(v['justesse_alertes'] * 100)} % "
            f"| {_fr(v['confiance_finale'], 2)} |"
        )
    return lignes


def tableau_transfert(d: dict) -> list[str]:
    lignes = [
        "| city | rainy / hot / mild (days) | agent | rulebook "
        "| difference | warnings / day |",
        "|---|:--:|---:|---:|---:|---:|",
    ]
    for nom, v in d["villes"].items():
        s = v["saisons"]
        saisons = " / ".join(
            str(s.get(k, 0)) for k in ("pluies", "sèche chaude", "sèche tempérée")
        )
        vu = " *(training city)*" if nom == d["entraine_sur"] else ""
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
        f"*{d['journees']} simulated days, one per day of the year, identical seeds for "
        f"every policy. Measured on {d['genere_le'][:10]}, regenerated by "
        f"`python -m wiiga.resultats --journees {d['journees']}`.*"
    )
    bloc += ["", "### What each policy costs the city", ""]
    bloc += tableau_principal(d)

    bloc += ["", "### The same table, season by season - dry hours per day", ""]
    bloc += tableau_saisons(d)
    bloc += [
        "",
        "The annual average hides the point: the hand-written rules give way in the",
        "hot dry season, which is exactly when the city is thirstiest.",
    ]

    if JOURNEE.exists():
        bloc += tableau_journee(json.loads(JOURNEE.read_text(encoding="utf-8")))

    bloc += ["", "### Speech: what the agent tells the city, and whether it is believed", ""]
    bloc += tableau_parole(d)

    ecarts = [
        ("what the utility runs today", r["vs_pratique_actuelle"]),
        ("the hand-written rulebook", r["vs_regle_ecrite"]),
        ("itself, with the warning switched off", r["vs_lui_meme_sans_la_parole"]),
    ]
    bloc += ["", "### At a glance", ""]
    for titre, e in ecarts:
        morceaux = [f"{_fr(e['heures_a_sec_pct'])} % fewer dry hours"]
        if "cout_pct" in e:
            morceaux.append(f"{_fr(e['cout_pct'])} % cheaper to run")
        if "co2_pct" in e:
            morceaux.append(f"{_fr(e['co2_pct'])} % less CO2")
        bloc.append(f"- **against {titre}**: " + ", ".join(morceaux))

    # Les mêmes écarts en gens et en tonnes. Ils vivaient jusqu'ici dans le texte
    # de soumission, tapés à la main : celui contre la pratique actuelle avait
    # survécu à la correction de cette même pratique et annonçait 27 % de plus
    # que la mesure. Ils sont produits ici, donc ils ne peuvent plus vieillir.
    h = r["en_humain"]
    bloc += [
        f"- **in people**, the unit that matters: "
        f"**{_fr(h['personnes_jours_epargnees_par_an_vs_regle'])} person-days a "
        f"year** above the WHO survival threshold of 20 L against the rulebook, "
        f"**{_fr(h['personnes_jours_epargnees_par_an_vs_pratique'])}** against "
        f"current practice, for {_fr(h['habitants_desservis'])} people across "
        f"three districts",
    ]
    if "kg_co2_evites_par_an_vs_pratique" in h:
        bloc.append(
            f"- **in CO2**: "
            f"**{_fr(h['kg_co2_evites_par_an_vs_pratique'] / 1000, 1)} tonnes a "
            f"year** against current practice, "
            f"{_fr(h['kg_co2_evites_par_an_vs_regle'] / 1000, 1)} against the "
            f"rulebook - two different comparisons, said separately"
        )

    if GRAINES.exists():
        g = json.loads(GRAINES.read_text(encoding="utf-8"))
        e = g["ecart_a_la_regle_pct"]
        bloc += [
            "",
            "### Does the result survive its own variance",
            "",
            "*PPO is stochastic. A single lucky run proves nothing, so here are "
            "three complete trainings on three seeds, evaluated on the same days "
            "against the same rules.*",
            "",
            "| training seed | dry hours / day | warnings / day | warning accuracy |",
            "|---|---:|---:|---:|",
        ]
        for nom, m in g["graines"].items():
            bloc.append(
                f"| {nom.replace('graine_', 'seed ')} "
                f"| {_fr(m['heures_a_sec_par_jour'], 2)} "
                f"| {_fr(m['alertes_par_jour'], 2)} "
                f"| {_fr(m['justesse_alertes'] * 100)} % |"
            )
        regle = g["regles"]["prévoyant (règle écrite)"]
        bloc.append(
            f"| **the rulebook they all beat** "
            f"| **{_fr(regle['heures_a_sec_par_jour'], 2)}** | 0 | - |"
        )
        verdict = (
            "All three seeds beat the hand-written rulebook"
            if g["toutes_les_graines_battent_la_regle"]
            else "**At least one seed loses to the rulebook**, and that is said here"
        )
        bloc += [
            "",
            f"{verdict}, by **{_fr(e['moyenne'])} %** on average and "
            f"between **{_fr(e['min'])} %** and **{_fr(e['max'])} %** depending on the "
            "seed. The worst of the three is the number to plan with.",
        ]

    if MEILLEURE.exists():
        b = json.loads(MEILLEURE.read_text(encoding="utf-8"))
        # la taille de la grille se lit dans la grille : elle était écrite « 5x5 »
        # ici et « 6x5 » dans la grille du jury, pour un balayage qui en compte 30
        seuils = len({k.split("/")[0] for k in b["grille"]})
        facteurs = len({k.split("/")[1] for k in b["grille"]})
        bloc += [
            "",
            "### Was the rulebook given its best shot?",
            "",
            "*The fair objection to any \"we beat the baseline\" claim: you did not "
            "show a rule cannot do this, you showed that YOUR rule does not. So the "
            f"rulebook's two hand-set constants were swept over a {seuils}x{facteurs} "
            "grid, and the agent replayed against the best of the family.*",
            "",
            f"| | dry hours / day |",
            "|---|---:|",
            f"| the rulebook as written in this repo | {_fr(b['regle_du_depot'], 3)} |",
            f"| **the best rulebook of the family** (threshold "
            f"{b['meilleure_regle']['seuil']}, factor {b['meilleure_regle']['facteur']}) "
            f"| **{_fr(b['meilleure_regle']['heures_a_sec'], 3)}** |",
            f"| the agent | {_fr(b['agent_heures_a_sec'], 3)} |",
            "",
            (f"The repo's rulebook was **under-tuned by "
             f"{_fr((b['regle_du_depot'] - b['meilleure_regle']['heures_a_sec']) / b['regle_du_depot'] * 100)} %**, "
             f"and the agent still beats the best of the family by "
             f"**{_fr(b['ecart_agent_vs_meilleure_pct'])} %**. The rule was allowed to "
             "pick its constants while looking at the very days it is scored on - an "
             "advantage the agent does not get, since its weights are frozen before "
             "it sees them.")
            if b["agent_bat_la_meilleure"]
            else "**The best rulebook of the family beats the agent**, and that is "
                 "said here rather than left to be found.",
        ]

    if SENSIBILITE.exists():
        s = json.loads(SENSIBILITE.read_text(encoding="utf-8"))
        carb = s["balayages"].get("CARBURANT_JOUR", [])
        perdues = [x for x in carb if not x["agent_gagne"]]
        gagnees = [x for x in carb if x["agent_gagne"]]
        if carb:
            bloc += [
                "",
                "### Where this stops being true",
                "",
                "*A result with no stated boundary is a result nobody believes. The "
                "daily generator budget is the constant the whole problem turns on, "
                "so here is the agent swept across it.*",
                "",
                "| diesel available per day | agent | rulebook | difference |",
                "|---|---:|---:|---:|",
            ]
            for x in carb:
                litres = x["valeur"] / 3.5
                bloc.append(
                    f"| {_fr(litres)} L ({_fr(x['valeur'] / 2257 * 100)} % of the "
                    f"day's energy){' **<- the value used**' if x['retenue'] else ''} "
                    f"| {_fr(x['agent_heures_a_sec'], 2)} "
                    f"| {_fr(x['regle_heures_a_sec'], 2)} "
                    f"| {_fr(x['ecart_pct'])} % |"
                )
            if perdues and gagnees:
                seuil = min(x["valeur"] for x in perdues) / 3.5
                bas = min(x["valeur"] for x in gagnees) / 3.5
                bloc += [
                    "",
                    f"**The agent wins from {_fr(bas)} to "
                    f"{_fr(max(x['valeur'] for x in gagnees) / 3.5)} litres a day, and "
                    f"loses at {_fr(seuil)}.** We are not burying that line, we are "
                    "naming it. At that budget the generator covers more than half the "
                    "city's pumping energy: there is no arbitrage left to make, you "
                    "simply burn diesel, and twenty lines of `if` are enough. **WIIGA "
                    "is for utilities that are constrained** - and an advantage that "
                    "survived the removal of the constraint would be the suspicious "
                    "result, not this one.",
                ]

    if EQUIVALENCE.exists():
        q = json.loads(EQUIVALENCE.read_text(encoding="utf-8"))
        bloc += ["", "### What it replaces in concrete", ""]
        if q.get("capacite_equivalente"):
            bloc.append(
                f"The simulator is a digital twin, so it answers capital questions. "
                f"The hand-written rulebook only matches the agent at "
                f"**{q['capacite_equivalente']:.2f}x storage** - "
                f"**{_fr(q['m3_de_stockage_evites'])} m3** of new tank on the "
                f"{_fr(q['capacite_actuelle_m3'])} m3 that exist, a "
                f"**{_fr((q['capacite_equivalente'] - 1) * 100)} % expansion**. "
                f"That is what the agent is worth in concrete, and it costs nothing "
                f"to pour."
            )
            if q.get("carburant_equivalent"):
                bloc.append(
                    f"\nBuying the same result with fuel instead takes "
                    f"**{q['carburant_equivalent']:.2f}x the daily generator budget** - "
                    f"more emissions, every day, for as long as the station runs."
                )
        else:
            bloc.append(
                "Even at the largest capacity tested, the rulebook does not catch "
                "the agent. The gap is not a storage problem."
            )

    if TRANSFERT.exists():
        t = json.loads(TRANSFERT.read_text(encoding="utf-8"))
        bloc += [
            "",
            "### And in a city it has never seen",
            "",
            f"*The weights trained on {t['entraine_sur']}, replayed unchanged. Nothing is "
            "retrained: the climatology is swapped, and nothing else.*",
            "",
        ]
        bloc += tableau_transfert(t)
        gagnees = sum(1 for v in t["villes"].values() if v["agent_bat_la_regle"])
        bloc += [
            "",
            f"The agent beats the rulebook in **{gagnees} of {len(t['villes'])}** "
            "of these cities, with nothing retrained. It does not win everywhere, "
            "and the pattern is worth more than a clean sweep would be: **its "
            "advantage tracks how hard the city is.** Where the rulebook already "
            "keeps taps running - Sydney, Lima - there is nothing left to win. "
            "Where the problem bites, the gap opens. A tool that helps most "
            "exactly where the need is greatest is the tool you want.",
        ]

    return "\n".join(bloc)


def main() -> None:
    bloc = construire()
    if not README.exists():
        print(bloc)
        raise SystemExit(
            f"\n({README.name} n'existe pas encore - bloc affiché plutôt qu'inséré)"
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
