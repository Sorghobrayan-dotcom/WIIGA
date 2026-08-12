"""Et si la regle ecrite etait mieux reglee que la notre ?

L'objection est la plus solide qu'on puisse faire au resultat principal, et elle
tient en une phrase : *vous n'avez pas montre qu'une regle ne peut pas arbitrer
quatre horizons, vous avez montre que VOTRE regle ne le fait pas.*

`prevoyant` porte deux constantes posees a la main. Le seuil de risque au-dela
duquel elle declare l'urgence (0,45), et le facteur dont elle gonfle son pompage
quand l'urgence est declaree (1,8). Rien dans le depot ne dit qu'elles ont ete
cherchees. Tant qu'on ne les a pas balayees, l'agent est compare a une regle
prise au hasard dans une famille.

Ce module cherche la **meilleure** de la famille sur une grille, puis rejoue
l'agent contre elle. Deux issues, toutes deux publiables :

- l'agent gagne encore, et l'argument devient definitif ;
- la meilleure regle rattrape l'agent, et il faut le dire tout de suite plutot
  que de laisser un lecteur le trouver.

Le balayage joue la regle sur les memes journees et les memes graines que
l'agent. On lui accorde donc exactement ce qu'on s'accorde, y compris le droit
de choisir ses constantes en connaissant le banc d'essai - un avantage que
l'agent n'a pas, puisque ses poids sont fixes avant de voir ces journees-la.

Execution : `python -m wiiga.meilleure_regle`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .env import HORIZON_RESEAU, SOURCES, WiigaEnv, solaire_horaire
from .resultats import mesurer

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "meilleure_regle.json"

#: La grille. Le seuil de risque va de tres nerveux (0,05 : on declare l'urgence
#: au moindre nuage) a tres flegmatique (0,75 : il faut une quasi-certitude). Le
#: facteur de gonflement va de 1,0 (aucune reaction) a 3,0 (on remplit tout ce
#: qu'on peut). La valeur du depot, 0,45 et 1,8, est dans la grille.
SEUILS = (0.05, 0.15, 0.30, 0.45, 0.60, 0.75)
FACTEURS = (1.0, 1.4, 1.8, 2.4, 3.0)


def regle(seuil: float, facteur: float):
    """La meme heuristique que `baselines.prevoyant`, ses deux constantes libres."""

    def jouer(obs, env: WiigaEnv) -> np.ndarray:
        heure = env.heure
        soleil = solaire_horaire(heure)
        reseau_up = env.reseau.disponible(heure)
        risque = float(env.reseau.prevision(heure, HORIZON_RESEAU).max())
        urgence = risque > seuil

        if soleil > 0.2:
            source = "solaire"
        elif reseau_up:
            source = "reseau"
        else:
            source = "diesel"

        a = []
        for z in env.zones:
            manque = 1.0 - z.remplissage
            p = float(np.clip(manque * (facteur if urgence else 1.0), 0.1, 1.0))
            a.append(p)
            a.append((SOURCES.index(source) + 0.5) / 3.0)
        a.append(0.0)  # ne passe jamais la main
        a.append(0.0)  # n'alerte jamais
        return np.array(a, dtype=np.float32)

    return jouer


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=120)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--modele", default="agents/graine_0")
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .train import politique_agent

    agent = mesurer(politique_agent(PPO.load(args.modele)), args.journees, args.seed)
    cible = agent["heures_a_sec_par_jour"]

    print(f"\nagent : {cible:.3f} heure a sec par jour")
    print(f"balayage de la regle ecrite sur {len(SEUILS)}x{len(FACTEURS)} reglages\n")
    print(f"{'seuil \\ facteur':>16}" + "".join(f"{f:>8.1f}" for f in FACTEURS))
    print("-" * (16 + 8 * len(FACTEURS)))

    grille, meilleure = {}, None
    for s in SEUILS:
        ligne = f"{s:>16.2f}"
        for f in FACTEURS:
            m = mesurer(regle(s, f), args.journees, args.seed)
            h = m["heures_a_sec_par_jour"]
            grille[f"{s}/{f}"] = m
            if meilleure is None or h < meilleure[2]:
                meilleure = (s, f, h, m)
            marque = "*" if (s, f) == (0.45, 1.8) else " "
            ligne += f"{h:>7.2f}{marque}"
        print(ligne)

    s, f, h, m = meilleure
    ecart = (h - cible) / h * 100 if h > 0 else 0.0
    depot = grille["0.45/1.8"]["heures_a_sec_par_jour"]

    print("\n* = les constantes du depot (0,45 et 1,8)")
    print(f"\nmeilleure regle de la famille : seuil {s}, facteur {f} -> {h:.3f} h a sec")
    print(f"celle du depot                : seuil 0.45, facteur 1.8 -> {depot:.3f} h a sec")
    print(f"l'agent                       : {cible:.3f} h a sec")
    print(
        f"\nl'agent bat la MEILLEURE regle de la famille de {ecart:.0f} %"
        if cible <= h
        else f"\nla meilleure regle de la famille bat l'agent - a dire tel quel"
    )
    if depot > h:
        print(f"(la regle du depot etait sous-reglee de {(depot - h) / depot * 100:.0f} %,"
              f" et le resultat tient quand meme)")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                "modele": args.modele,
                "agent_heures_a_sec": cible,
                "regle_du_depot": depot,
                "meilleure_regle": {"seuil": s, "facteur": f, "heures_a_sec": h},
                "ecart_agent_vs_meilleure_pct": ecart,
                "agent_bat_la_meilleure": bool(cible <= h),
                "grille": {k: v["heures_a_sec_par_jour"] for k, v in grille.items()},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\necrit dans {SORTIE}")


if __name__ == "__main__":
    main()
