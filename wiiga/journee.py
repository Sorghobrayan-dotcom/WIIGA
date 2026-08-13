"""La journee que le README raconte, produite par une commande.

Le README s'ouvre sur une journee plutot que sur une moyenne annuelle, parce
qu'une moyenne ne se represente pas. Mais une journee racontee a la main ne se
verifie pas : la premiere version de ce paragraphe citait une date, des litres
et un nombre de personnes qu'aucune commande du depot ne redonnait, et qui ne
decrivaient meme plus la journee que la console rejoue. Un chiffre qui survit a
la mesure qui l'a produit est exactement ce que le reste du projet s'interdit.

Ce module produit les deux seules choses dont ce paragraphe a besoin :

- **la journee de la console** - celle qu'un visiteur peut rejouer heure par
  heure, la mediane de la saison seche chaude a Ouagadougou. Ce que la regle
  ecrite y laisse sans eau, ce que l'agent y laisse, et les heures ou il passe
  la main. C'est le meme jour et la meme graine que `demo/scenarios.py`, parce
  que la definition vit ici et que la console l'importe.
- **ou l'ecart se concentre dans l'annee** - les journees ou l'agent apporte le
  plus, rejouees sur les memes jours et les memes graines que le tableau annuel
  de `resultats.py`. Ecrire que la valeur se concentre sur les jours les plus
  durs est une affirmation mesurable : elle est donc mesuree ici plutot
  qu'affirmee dans le texte.

La journee retenue est la **mediane** de sa saison, pas la meilleure trouvee.
Choisir la journee ou l'ecart est maximal pour illustrer, puis publier la
moyenne annuelle a cote, serait une facon discrete de mentir ; le classement des
plus gros ecarts est publie separement, en disant que c'en est un.

Execution : `python -m wiiga.journee`
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .baselines import POLITIQUES
from .calendrier import OUAGADOUGOU, Climat, _jour_vers_date, journee
from .env import WiigaEnv
from .resultats import LITRES_SURVIE
from .tarifs import tarif_de

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "journee.json"

#: La graine de la console. Elle fixe les coupures de la journee rejouee : deux
#: graines differentes ne racontent pas la meme journee, donc le chiffre publie
#: et la page doivent partager celle-ci. `demo/scenarios.py` l'importe d'ici.
GRAINE_CONSOLE = 24

#: La saison sur laquelle le README ouvre. C'est le regime ou les regles ecrites
#: cedent, et le seul ou l'ecart vaut la peine d'etre raconte a l'heure pres.
SAISON_VEDETTE = "sèche chaude"

#: Les mois en toutes lettres, en anglais, ecrits ici plutot que laisses a
#: `strftime` : le nom du mois dependrait alors de la locale de la machine, et la
#: page publiee afficherait « 25 fevrier » ou « 25 February » selon qui la
#: construit. Le README et la page lisent la meme chaine que ce module produit.
MOIS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def date_en(jour: int) -> str:
    """Le jour de l'annee ecrit comme le texte l'ecrit : « 25 February »."""
    d = _jour_vers_date(jour)
    return f"{d.day} {MOIS_EN[d.month - 1]}"


def journee_type(climat: Climat, saison: str) -> int | None:
    """Le jour du milieu d'un regime, pour eviter les bords.

    On prend la mediane des jours de cette saison plutot que le premier venu :
    un jour de transition raconterait mal le regime qu'il est cense illustrer.
    """
    jours = [j for j in range(365) if journee(j, climat).saison == saison]
    return jours[len(jours) // 2] if jours else None


def rejouer(politique, climat: Climat, tarif, jour: int, graine: int = GRAINE_CONSOLE):
    """Une politique, une journee fixee, et tout ce qui s'y est passe.

    Rend l'environnement et le bilan de fin de journee : `env.journal` porte les
    vingt-quatre heures, et c'est la seule facon d'aller relire ce que l'agent a
    fait a 13 h. La console passe par ici aussi, pour qu'il n'existe qu'un seul
    chemin de rejeu.
    """
    env = WiigaEnv(seed=0, climat=climat, tarif=tarif)
    env.jour_fixe = jour
    obs, _ = env.reset(seed=graine)
    fini = False
    while not fini:
        obs, _, arret, tronque, info = env.step(politique(obs, env))
        fini = arret or tronque
    return env, info


def par_jour(politique, journees: int, seed: int) -> list[dict]:
    """L'annee jour par jour, dans la convention exacte de `resultats.mesurer`.

    Meme environnement neuf par politique, meme `jour_fixe`, meme graine par
    journee. Sans cela l'ecart lu ici ne serait pas celui du tableau annuel, et
    deux chiffres du meme depot se contrediraient.
    """
    env = WiigaEnv(seed=0)
    jours = []
    for j in range(journees):
        env.jour_fixe = j % 365
        obs, _ = env.reset(seed=seed + j)
        fini = False
        while not fini:
            obs, _, arret, tronque, info = env.step(politique(obs, env))
            fini = arret or tronque
        jours.append(
            {
                "jour": j % 365,
                "date": _jour_vers_date(j % 365).strftime("%d/%m"),
                "date_en": date_en(j % 365),
                "saison": info["saison"],
                "temperature": round(journee(j % 365, OUAGADOUGOU).temperature, 1),
                "litres_manquants": float(info["litres_manquants"]),
                "heures_a_sec": int(info["heures_a_sec"]),
            }
        )
    return jours


def moments(journal: list[dict]) -> dict:
    """Les trois moments que le texte commente, relus dans le journal.

    Ils sont extraits plutot que recopies : si l'agent change d'avis a
    l'entrainement suivant, le README le dira au lieu de raconter l'ancien.
    """

    def heure(h: int) -> dict:
        e = journal[h]
        return {
            "puissances": [round(float(x), 2) for x in e["puissances"]],
            "sources": list(e["sources"]),
            "cuve_la_plus_basse": round(float(min(e["remplissages"])), 2),
        }

    passees = [e["heure"] for e in journal if e["passe_la_main"]]
    return {
        "midi": heure(13),
        "soir": heure(19),
        "heures_ou_il_passe_la_main": passees,
        "reprend_la_main_a": (max(passees) + 1) if passees else None,
        "cuves_apres_la_premiere_main_passee": (
            [round(float(x), 2) for x in journal[passees[0]]["remplissages"]]
            if passees
            else []
        ),
    }


def main() -> None:
    from .train import MODELE_PUBLIE

    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=365)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--modele", default=MODELE_PUBLIE)
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .train import politique_agent

    agent = politique_agent(PPO.load(args.modele))
    regle = POLITIQUES["prévoyant (règle écrite)"]
    tarif, _ = tarif_de("Ouagadougou")

    # ------------------------------------------------------- la journee montree
    jour = journee_type(OUAGADOUGOU, SAISON_VEDETTE)
    d = journee(jour, OUAGADOUGOU)
    env_a, info_a = rejouer(agent, OUAGADOUGOU, tarif, jour)
    _, info_r = rejouer(regle, OUAGADOUGOU, tarif, jour)

    console = {
        "jour": jour,
        "date": _jour_vers_date(jour).strftime("%d/%m"),
        "date_en": date_en(jour),
        "saison": SAISON_VEDETTE,
        "temperature": round(d.temperature, 1),
        "graine": GRAINE_CONSOLE,
        "agent": {
            "litres_manquants": round(float(info_a["litres_manquants"])),
            "personnes_sous_le_seuil": round(
                float(info_a["litres_manquants"]) / LITRES_SURVIE
            ),
            "heures_a_sec": int(info_a["heures_a_sec"]),
        },
        "regle_ecrite": {
            "litres_manquants": round(float(info_r["litres_manquants"])),
            "personnes_sous_le_seuil": round(
                float(info_r["litres_manquants"]) / LITRES_SURVIE
            ),
            "heures_a_sec": int(info_r["heures_a_sec"]),
        },
        "moments": moments(env_a.journal),
    }

    print(f"\njournee de la console : jour {jour}, "
          f"{console['date']}, {console['temperature']} C, graine {GRAINE_CONSOLE}")
    print(f"  regle ecrite : {console['regle_ecrite']['litres_manquants']:>8} L manquants"
          f" -> {console['regle_ecrite']['personnes_sous_le_seuil']:>6} personnes sous 20 L")
    print(f"  agent        : {console['agent']['litres_manquants']:>8} L manquants"
          f" -> {console['agent']['personnes_sous_le_seuil']:>6} personnes sous 20 L")
    m = console["moments"]
    print(f"  13 h : pompes {m['midi']['puissances']} sur {m['midi']['sources'][0]}")
    print(f"  19 h : pompes {m['soir']['puissances']}, "
          f"cuve la plus basse {m['soir']['cuve_la_plus_basse']:.0%}")
    print(f"  passe la main a {m['heures_ou_il_passe_la_main']} h, "
          f"reprend a {m['reprend_la_main_a']} h")

    # -------------------------------------------------- ou l'ecart se concentre
    print(f"\nrejeu de {args.journees} journees pour les deux politiques...")
    jours_a = par_jour(agent, args.journees, args.seed)
    jours_r = par_jour(regle, args.journees, args.seed)

    ecarts = [
        {
            "date": a["date"],
            "date_en": a["date_en"],
            "saison": a["saison"],
            "temperature": a["temperature"],
            "personnes_epargnees": (r["litres_manquants"] - a["litres_manquants"])
            / LITRES_SURVIE,
            "regle_personnes": r["litres_manquants"] / LITRES_SURVIE,
            "agent_personnes": a["litres_manquants"] / LITRES_SURVIE,
        }
        for a, r in zip(jours_a, jours_r)
    ]
    classement = sorted(ecarts, key=lambda x: -x["personnes_epargnees"])
    total = sum(max(0.0, x["personnes_epargnees"]) for x in ecarts)
    par_saison = Counter()
    for x in ecarts:
        par_saison[x["saison"]] += max(0.0, x["personnes_epargnees"])

    cinq = classement[:5]
    print(f"\nles cinq journees ou l'agent apporte le plus")
    print(f"{'date':>8}{'saison':>16}{'C':>7}{'regle':>9}{'agent':>8}{'ecart':>9}")
    print("-" * 57)
    for x in cinq:
        print(f"{x['date']:>8}{x['saison']:>16}{x['temperature']:>7.1f}"
              f"{x['regle_personnes']:>9.0f}{x['agent_personnes']:>8.0f}"
              f"{x['personnes_epargnees']:>9.0f}")

    print("\npart de l'ecart annuel par saison")
    for s, v in par_saison.most_common():
        print(f"  {s:<16}{v / total * 100 if total else 0:>6.1f} %")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                "modele": args.modele,
                "journee_de_la_console": console,
                "cinq_plus_gros_ecarts": cinq,
                "part_de_l_ecart_par_saison": {
                    s: (v / total * 100 if total else 0.0)
                    for s, v in par_saison.most_common()
                },
                "temperatures_des_cinq": [x["temperature"] for x in cinq],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\necrit dans {SORTIE}")


if __name__ == "__main__":
    main()
