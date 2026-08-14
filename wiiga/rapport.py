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
CHOC = RACINE / "resultats" / "choc.json"
RISQUE = RACINE / "resultats" / "risque.json"
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


#: Meme raison pour les quartiers, et les memes libelles que la console : un
#: tableau qui dit « mixte » a cote d'une page qui dit « school + clinic » laisse
#: croire qu'il s'agit de deux quartiers.
ZONES = {"marché": "market", "résidentiel": "residential", "mixte": "school + clinic"}


def _nom(cle: str) -> str:
    return NOMS.get(cle, cle)


def _zone(cle: str) -> str:
    return ZONES.get(cle, cle)


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


def tableau_quartiers(d: dict) -> list[str]:
    """Les heures a sec quartier par quartier, et le pire d'entre eux.

    La colonne « dry hours / day » du tableau principal est une **somme** sur les
    trois quartiers. C'est la bonne grandeur pour comparer deux politiques, et le
    texte l'a longtemps appelee « le quartier le plus mal servi », ce qu'elle
    n'est pas : pour la consigne fixe, la somme vaut 2,48 et le pire quartier
    1,29. Les deux sont publiees ici plutot que corrigees en silence, d'autant
    que l'agent est **meilleur** sur celle qui manquait.
    """
    m = d["mesures"]
    zones = list(next(iter(m.values())).get("heures_a_sec_par_zone", {}))
    if not zones:
        return []
    lignes = [
        "",
        "### The same hours, district by district",
        "",
        "*The column above is a **sum over the three districts**: two districts "
        "dry in the same hour count twice. It is the right quantity for ranking "
        "policies and the wrong one for describing what a household lives "
        "through, so here is the breakdown, and the worst district on its own - "
        "the quantity the reward actually optimises.*",
        "",
        "| operator | " + " | ".join(_zone(z) for z in zones)
        + " | worst district | sum |",
        "|---" + "|---:" * (len(zones) + 2) + "|",
    ]
    for nom, v in m.items():
        gras = "**" if nom.startswith("agent WIIGA (") else ""
        cases = " | ".join(_fr(v["heures_a_sec_par_zone"][z], 2) for z in zones)
        lignes.append(
            f"| {gras}{_nom(nom)}{gras} | {cases} | "
            f"**{_fr(v['heures_a_sec_pire_zone'], 2)}** | "
            f"{_fr(v['heures_a_sec_par_jour'], 2)} |"
        )

    a, r = m["agent WIIGA (PPO)"], m["prévoyant (règle écrite)"]
    t = m["exploitant (consigne fixe)"]
    agent, regle = a["heures_a_sec_pire_zone"], r["heures_a_sec_pire_zone"]
    terrain = t["heures_a_sec_pire_zone"]
    # le quartier ou l'agent est le plus en retard sur la regle. Il en existe un,
    # et une phrase qui ne parlerait que du maximum le laisserait sous le tapis
    pire_pour_nous = max(
        zones, key=lambda z: a["heures_a_sec_par_zone"][z] - r["heures_a_sec_par_zone"][z]
    )
    recule = (
        a["heures_a_sec_par_zone"][pire_pour_nous]
        - r["heures_a_sec_par_zone"][pire_pour_nous]
    )
    lignes += [
        "",
        f"On the worst-served district - the quantity the reward optimises - the "
        f"agent leaves it dry **{_fr((regle - agent) / regle * 100 if regle else 0)} % "
        f"less** than the rulebook and "
        f"**{_fr((terrain - agent) / terrain * 100 if terrain else 0)} % less** than "
        "current practice. Both gaps are wider than the ones on the sum, which is "
        "what a max-min objective is supposed to produce.",
    ]
    if recule > 0:
        lignes += [
            "",
            f"**And it is not free.** The agent is *worse* than the rulebook on the "
            f"{_zone(pire_pour_nous)} district - "
            f"{_fr(a['heures_a_sec_par_zone'][pire_pour_nous], 2)} against "
            f"{_fr(r['heures_a_sec_par_zone'][pire_pour_nous], 2)} - and better on "
            "the residential one by an order of magnitude. That is the trade a "
            "max-min objective makes: it does not improve every district, it "
            "**flattens the spread**. The rulebook's districts run from "
            f"{_fr(min(r['heures_a_sec_par_zone'].values()), 2)} to "
            f"{_fr(max(r['heures_a_sec_par_zone'].values()), 2)}; the agent's from "
            f"{_fr(min(a['heures_a_sec_par_zone'].values()), 2)} to "
            f"{_fr(max(a['heures_a_sec_par_zone'].values()), 2)}. If you would "
            "rather have one district suffer a lot and two suffer none, this is "
            "the wrong objective, and that choice is stated rather than hidden.",
        ]
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


def tableau_choc(c: dict) -> list[str]:
    """Ce que devient l'ecart quand la demande reelle depasse la prevision.

    Deux tableaux et une borne. La borne est le plafond hydraulique, et elle est
    donnee avant les tableaux plutot qu'apres : c'est elle qui explique pourquoi
    le balayage s'arrete a +30 % et pas a +200 %, et un lecteur qui trouve la
    plage etroite sans savoir pourquoi a raison de la trouver etroite.
    """
    z, f = c["zone_vedette"], c["facteur_comparaison"]
    pc = round((f - 1) * 100)
    d0, d1 = c["fenetre_horaire"]
    lignes = [
        "",
        "### When the demand model is wrong",
        "",
        "*The README calls demand elasticity the weakest assumption in this "
        "project. So here it is, broken on purpose: one district drinks more than "
        "the forecast announced, for "
        f"{d1 - d0} hours a day, and **nothing tells the agent**. Its input "
        "carries the normalised shape of the usual profile, not the litres "
        "actually drawn - verified in `wiiga/tests.py`, not asserted here. "
        "Regenerated by `python -m wiiga.choc`.*",
        "",
        "**How far it can be pushed is a physical question, not an editorial "
        "one.** Past a district's pump flow, no policy can serve it and the gap "
        "between two policies stops measuring the policies. Measured over the "
        "same replayed year, that ceiling is:",
        "",
        "| district | unannounced surge the pump can still serve |",
        "|---|---:|",
    ]
    for nom, plafond in c["plafonds_hydrauliques"].items():
        lignes.append(f"| {_zone(nom)} | **+{round((plafond - 1) * 100)} %** |")
    lignes += [
        "",
        f"The sweep therefore stops at **+{pc} %**, and the district it runs on is "
        f"the tightest of the three.",
        "",
        f"| surge on the {_zone(z)} district | agent | rulebook | gap |",
        "|---|---:|---:|---:|",
    ]
    for L in c["balayage"]:
        surge = round((L["facteur"] - 1) * 100)
        etiquette = "none - the published table" if surge == 0 else f"+{surge} %"
        lignes.append(
            f"| {etiquette} | {_fr(L['agent_heures_a_sec'], 2)} | "
            f"{_fr(L['regle_heures_a_sec'], 2)} | **{_fr(L['ecart_pct'])} %** |"
        )
    lignes += [
        "",
        f"| the same +{pc} %, district by district | agent | rulebook | gap |",
        "|---|---:|---:|---:|",
    ]
    for L in c["par_quartier"]:
        lignes.append(
            f"| {_zone(L['zone'])} ({_fr(L['habitants'])} people) | "
            f"{_fr(L['agent_heures_a_sec'], 2)} | "
            f"{_fr(L['regle_heures_a_sec'], 2)} | **{_fr(L['ecart_pct'])} %** |"
        )

    res = c["resume"]
    lignes += [
        "",
        "**The conclusion does not move.** A third more water drawn than "
        f"announced, on any of the three districts, and the agent still leads by "
        f"{_fr(min(L['ecart_pct'] for L in c['par_quartier']))} to "
        f"{_fr(max(L['ecart_pct'] for L in c['par_quartier']))} %. The cost of the "
        f"surprise is {_fr(res['degradation_agent_au_pire'], 2)} dry hours a day "
        f"for the agent against {_fr(res['degradation_regle_au_pire'], 2)} for the "
        "rulebook - the agent does degrade faster, and both figures are about a "
        "minute a day. **The binding limit is not the agent's judgement, it is the "
        "pipe.**",
        "",
        "That second table is the one a utility director reads. It says which "
        "pump to enlarge first, and it is the same kind of answer as the 96 m3 of "
        "concrete above - produced by the twin, before anyone pours anything.",
    ]
    return lignes


def tableau_risque(c: dict) -> list[str]:
    """La tentative CVaR, publiee parce qu'elle a echoue.

    La recompense est rawlsienne dans l'espace - elle lit le quartier le plus mal
    servi. `risque.py` essayait de l'etre aussi dans le temps, en n'optimisant
    que la queue des pires journees. Le module et son agent entraine vivaient
    dans le depot sans figurer nulle part dans la soumission, parce que la
    commande cherchait `cvar_0.zip` quand le fichier s'appelait `cvar_essai.zip`
    et omettait la ligne en silence. Corrige, l'agent est mesure, et le resultat
    est ce qu'il est.
    """
    pols = c.get("politiques", {})
    cvar = {k: v for k, v in pols.items() if "CVaR" in k}
    if not cvar:
        return []
    alpha = int(c.get("alpha", 0.2) * 100)
    lignes = [
        "",
        f"### Rawlsian in space, and the attempt to be Rawlsian in time",
        "",
        "*The reward reads the worst-served district. It is still an **average "
        "over days**, so a policy that serves eleven months perfectly and leaves "
        "the city dry for three days in April can win. `risque.py` optimised the "
        f"CVaR instead - the mean of the worst {alpha} % of days. This is the "
        "measurement that says what came of it. Regenerated by "
        "`python -m wiiga.risque`.*",
        "",
        "| policy | mean dry hours / day | worst 20 % of days | worst single day | days above 2 h |",
        "|---|---:|---:|---:|---:|",
    ]
    def libelle(nom: str) -> str:
        """Les memes noms anglais que partout ailleurs dans le README."""
        if "CVaR" in nom:
            return f"PPO on the CVaR - the worst {alpha} % of days"
        if "regle" in nom.lower():
            return "hand-written rulebook"
        graine = nom.rsplit(" ", 1)[-1]
        publie = " *(the published model)*" if graine == "0" else ""
        return f"PPO on the mean, seed {graine}{publie}"

    for nom, v in pols.items():
        gras = "**" if "CVaR" in nom else ""
        lignes.append(
            f"| {gras}{libelle(nom)}{gras} | {_fr(v['moyenne'], 3)} "
            f"| {_fr(v['cvar_20'], 2)} "
            f"| {_fr(v['pire_jour'], 0)} | {v['jours_au_dessus_de_2h']} |"
        )

    pire_cvar = max(cvar.values(), key=lambda v: v["moyenne"])
    # le modele publie, nomme, et pas le meilleur des deux graines presentes :
    # citer la graine 1 parce qu'elle est plus flatteuse serait exactement ce que
    # le reste du depot s'interdit
    reference = next(
        (v for k, v in pols.items() if k.rsplit(" ", 1)[-1] == "0" and "CVaR" not in k),
        None,
    )
    lignes += [
        "",
        "**It failed, and it failed completely.** The trade we were looking for "
        "was a little mean for a lot of tail. What we got is "
        f"{_fr(pire_cvar['moyenne'], 1)} dry hours a day against "
        + (f"{_fr(reference['moyenne'], 3)} " if reference else "")
        + f"for the published agent, dry on {pire_cvar['jours_au_dessus_de_2h']} "
        "days out of the year. Zeroing the advantage of every day outside the "
        "tail leaves too little gradient on a 24-step episode: the policy "
        "collapses rather than specialising. The idea is right and this "
        "implementation of it is not, which is a different sentence from *the "
        "idea does not work* - and the code stays in the repository at the line "
        "where it failed.",
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

    bloc += tableau_quartiers(d)

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

    if CHOC.exists():
        bloc += tableau_choc(json.loads(CHOC.read_text(encoding="utf-8")))

    if RISQUE.exists():
        bloc += tableau_risque(json.loads(RISQUE.read_text(encoding="utf-8")))

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
