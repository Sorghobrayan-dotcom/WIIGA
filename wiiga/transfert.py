"""L'agent tient-il dans une ville qu'il n'a jamais vue ?

« Scalable » est un mot que tout le monde écrit et que personne ne mesure. Le
sens qu'on lui donne ici est le seul qui engage : **les poids entraînés sur
Ouagadougou, rejoués tels quels sur des climats qui n'étaient pas dans
l'entraînement, contre la même règle écrite à la main.**

Rien n'est réentraîné, rien n'est réglé, aucune constante ne change. On remplace
douze températures, douze ensoleillements et douze pluviométries - c'est-à-dire
tout ce que le modèle sait de la géographie - et on regarde.

Les quatre villes ne sont pas choisies pour être faciles :

- **Chennai** - mousson du nord-est, saison des pluies en octobre-décembre au
  lieu de juillet-septembre. Le calendrier est décalé de trois mois.
- **Nairobi** - deux saisons des pluies par an au lieu d'une, et l'altitude
  écrase l'amplitude thermique dont l'agent se sert pour anticiper la demande.
- **Sydney** - hémisphère sud. Tout est inversé : le pic de chaleur tombe en
  janvier. Aucune règle apprise sur le numéro du jour ne peut survivre.
- **Lima** - désert côtier. Zéro jour de saison des pluies, et un ensoleillement
  qui s'effondre en hiver sans qu'il pleuve : la cuve-batterie tombe en panne
  pour une raison que l'agent n'a jamais rencontrée.

Ce que ça ne prouve pas, et qu'il vaut mieux écrire : la demande, les profils de
quartier et le régime de délestage restent ceux de Ouagadougou. On mesure le
transfert **climatique**, pas le transfert à un autre réseau d'eau.

Exécution : `python -m wiiga.transfert`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .baselines import prevoyant
from .env import WiigaEnv
from .ville import climat_de

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "transfert.json"

VILLES = ("Chennai", "Nairobi", "Sydney", "Lima")


def jouer(politique, climat, journees: int, seed: int) -> dict:
    """Une politique, une ville, `journees` journées réparties sur l'année."""
    env = WiigaEnv(seed=0, climat=climat)
    heures, cout, creux = 0, 0.0, []

    for j in range(journees):
        env.jour_fixe = j % 365
        obs, _ = env.reset(seed=seed + j)
        fini = False
        while not fini:
            obs, _, arret, tronque, info = env.step(politique(obs, env))
            fini = arret or tronque
        heures += info["heures_a_sec"]
        cout += info["cout_total"]
        creux.append(info["creux_journee"])

    return {
        "heures_a_sec_par_jour": heures / journees,
        "fcfa_par_jour": cout / journees,
        "creux_moyen": float(np.mean(creux)),
        "alertes_par_jour": info["alertes"] / journees,
        "justesse_alertes": info["justesse_alertes"],
        "confiance_finale": info["confiance"],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=365)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--modele", default="wiiga_agent")
    p.add_argument("--hors-ligne", action="store_true")
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .calendrier import OUAGADOUGOU, journee, seuils
    from .train import politique_agent

    agent = politique_agent(PPO.load(args.modele))

    villes = [OUAGADOUGOU] + [
        climat_de(n, hors_ligne=args.hors_ligne) for n in VILLES
    ]

    lignes, garde = {}, True
    print(f"\n{'ville':<14}{'saisons (j)':>22}{'agent':>9}{'règle':>9}{'écart':>9}"
          f"{'alertes/j':>11}{'justesse':>10}")
    print("-" * 84)

    for climat in villes:
        a = jouer(agent, climat, args.journees, args.seed)
        r = jouer(prevoyant, climat, args.journees, args.seed)
        gagne = a["heures_a_sec_par_jour"] <= r["heures_a_sec_par_jour"]
        garde = garde and gagne

        compte: dict[str, int] = {}
        for j in range(365):
            s = journee(j, climat).saison
            compte[s] = compte.get(s, 0) + 1
        resume_saisons = "/".join(
            str(compte.get(s, 0)) for s in ("pluies", "sèche chaude", "sèche tempérée")
        )

        base = r["heures_a_sec_par_jour"]
        ecart = 0.0 if base == 0 else (base - a["heures_a_sec_par_jour"]) / base * 100
        lignes[climat.nom] = {
            "agent": a,
            "regle_ecrite": r,
            "saisons": compte,
            "seuils": dict(
                zip(("pluie_mm", "soleil", "chaleur_c"), seuils(climat))
            ),
            "ecart_heures_a_sec_pct": ecart,
            "agent_bat_la_regle": gagne,
        }
        print(f"{climat.nom:<14}{resume_saisons:>22}"
              f"{a['heures_a_sec_par_jour']:>9.2f}{r['heures_a_sec_par_jour']:>9.2f}"
              f"{ecart:>8.0f}%{a['alertes_par_jour']:>11.2f}"
              f"{a['justesse_alertes'] * 100:>9.0f}%")

    print("\nsaisons : pluies / sèche chaude / sèche tempérée, jours par an")
    print("l'agent n'a vu que Ouagadougou à l'entraînement. Les quatre autres")
    print("villes sont des climats qu'il découvre au moment de l'évaluation.")
    print(
        "\nl'agent bat la règle écrite dans TOUTES les villes"
        if garde
        else "\nl'agent perd contre la règle dans au moins une ville - à dire tel quel"
    )

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                "entraine_sur": "Ouagadougou",
                "villes": lignes,
                "tient_partout": garde,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nécrit dans {SORTIE}")


if __name__ == "__main__":
    main()
