"""Combien de béton l'agent remplace-t-il ?

Un jumeau numérique ne sert pas seulement à entraîner. Il sert à **poser des
questions au réseau physique sans y toucher**, et celle-ci est la seule qu'un
directeur de régie se pose vraiment :

> De combien faudrait-il agrandir les cuves pour que la règle écrite serve la
> ville aussi bien que l'agent la sert avec les cuves actuelles ?

Tant qu'on répond « 34 % d'heures à sec en moins », on parle une langue
d'ingénieur. Dès qu'on répond « l'équivalent de 40 % de capacité de stockage en
plus », on parle d'un investissement qu'on n'a pas à faire, en mètres cubes de
béton et en francs.

La même question se pose pour le gasoil : quel budget carburant faudrait-il à la
règle écrite pour rattraper l'agent ? C'est de l'argent qui sort tous les mois,
et de la fumée qui ne sort pas.

**Ce que ça ne dit pas :** un vrai chiffrage demanderait un devis de génie civil,
et le prix du mètre cube de stockage varie du simple au triple selon le terrain.
On publie donc l'**équivalence physique** - combien de capacité, combien de
litres - et pas un prix inventé. Le lecteur qui connaît ses coûts fait la
multiplication lui-même.

Exécution : `python -m wiiga.equivalence`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .baselines import prevoyant
from .env import CARBURANT_JOUR, WiigaEnv

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "equivalence.json"

#: Les agrandissements de cuve essayés, en multiples de la capacité actuelle.
#: On monte jusqu'au double : au-delà, la question n'est plus « faut-il un peu
#: plus de béton » mais « faut-il un autre réseau ».
CUVES = (1.0, 1.15, 1.3, 1.5, 1.75, 2.0)

#: Les budgets de gasoil essayés, en multiples de la réserve quotidienne.
CARBURANTS = (1.0, 1.25, 1.5, 2.0, 3.0)


def jouer(politique, journees: int, seed: int, *, cuve: float = 1.0,
          carburant: float = 1.0) -> dict:
    """Une politique sur un réseau dont on a changé une caractéristique.

    `cuve` multiplie la capacité de stockage de chaque quartier, `carburant` la
    réserve quotidienne du groupe électrogène. Tout le reste est identique :
    mêmes journées, mêmes coupures, mêmes graines.
    """
    env = WiigaEnv(seed=0)
    heures, cout, manquants = 0, 0.0, 0.0

    for j in range(journees):
        env.jour_fixe = j % 365
        obs, _ = env.reset(seed=seed + j)

        if cuve != 1.0:
            # agrandir après le reset, en gardant le même taux de remplissage
            # initial : une cuve neuve n'arrive pas pleine
            for z in env.zones:
                part = z.remplissage
                z.capacite *= cuve
                z.volume = z.capacite * part
        if carburant != 1.0:
            env.carburant = CARBURANT_JOUR * carburant

        obs = env._observation()
        fini = False
        while not fini:
            obs, _, arret, tronque, info = env.step(politique(obs, env))
            fini = arret or tronque

        heures += info["heures_a_sec"]
        cout += info["cout_total"]
        manquants += info["litres_manquants"]

    return {
        "heures_a_sec_par_jour": heures / journees,
        "fcfa_par_jour": cout / journees,
        "litres_manquants_par_jour": manquants / journees,
    }


def seuil_atteint(courbe: list[tuple[float, float]], cible: float) -> float | None:
    """Le multiplicateur auquel la règle rattrape l'agent, par interpolation.

    `courbe` est une liste croissante de (multiplicateur, heures à sec). On
    cherche où elle croise `cible`. `None` si elle ne la croise jamais dans la
    plage essayée - auquel cas il faut le dire plutôt que d'extrapoler.
    """
    for (m0, h0), (m1, h1) in zip(courbe, courbe[1:]):
        if h0 >= cible >= h1 and h0 != h1:
            return m0 + (m1 - m0) * (h0 - cible) / (h0 - h1)
    return None


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

    reference = jouer(agent, args.journees, args.seed)
    cible = reference["heures_a_sec_par_jour"]
    print(f"\nl'agent, réseau tel quel : {cible:.3f} heure à sec par jour")
    print("on cherche ce qu'il faudrait ajouter à la règle écrite pour y arriver.\n")

    print(f"{'cuves':>8}{'règle : h sec/j':>18}{'FCFA/j':>10}")
    print("-" * 36)
    courbe_cuve = []
    for m in CUVES:
        r = jouer(prevoyant, args.journees, args.seed, cuve=m)
        courbe_cuve.append((m, r["heures_a_sec_par_jour"]))
        marque = "  <- rattrape" if r["heures_a_sec_par_jour"] <= cible else ""
        print(f"{m:>7.2f}x{r['heures_a_sec_par_jour']:>18.3f}"
              f"{r['fcfa_par_jour']:>10.0f}{marque}")

    print(f"\n{'gasoil':>8}{'règle : h sec/j':>18}{'FCFA/j':>10}")
    print("-" * 36)
    courbe_carb = []
    for m in CARBURANTS:
        r = jouer(prevoyant, args.journees, args.seed, carburant=m)
        courbe_carb.append((m, r["heures_a_sec_par_jour"]))
        marque = "  <- rattrape" if r["heures_a_sec_par_jour"] <= cible else ""
        print(f"{m:>7.2f}x{r['heures_a_sec_par_jour']:>18.3f}"
              f"{r['fcfa_par_jour']:>10.0f}{marque}")

    seuil_cuve = seuil_atteint(courbe_cuve, cible)
    seuil_carb = seuil_atteint(courbe_carb, cible)

    env = WiigaEnv(seed=0)
    env.reset(seed=0)
    capacite = sum(z.capacite for z in env.zones)

    print()
    if seuil_cuve:
        ajout = capacite * (seuil_cuve - 1.0)
        print(f"CUVES   : la règle écrite égale l'agent à {seuil_cuve:.2f}x de capacité,")
        print(f"          soit {ajout:.0f} m3 de stockage en plus sur les "
              f"{capacite:.0f} m3 existants ({(seuil_cuve-1)*100:.0f} %).")
        print(f"          L'agent vaut donc ce réservoir-là, et il ne coûte rien à couler.")
    else:
        print(f"CUVES   : même à {CUVES[-1]:.2f}x de capacité la règle écrite ne rattrape")
        print(f"          pas l'agent. L'écart n'est pas un problème de stockage.")

    if seuil_carb:
        print(f"GASOIL  : elle l'égale à {seuil_carb:.2f}x de réserve quotidienne, soit "
              f"{CARBURANT_JOUR*(seuil_carb-1):.0f} kWh de groupe en plus par jour.")
    else:
        print(f"GASOIL  : même à {CARBURANTS[-1]:.2f}x de réserve la règle écrite ne")
        print(f"          rattrape pas l'agent. Brûler plus ne remplace pas décider mieux.")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                # le modele qui sert de cible a tout le balayage : sans lui, la
                # phrase « 96 m3 de beton » ne dit pas de quel agent elle parle
                "modele": args.modele,
                "agent_reseau_actuel": reference,
                "capacite_actuelle_m3": capacite,
                "carburant_actuel_kwh": CARBURANT_JOUR,
                "regle_par_capacite": [
                    {"multiplicateur": m, "heures_a_sec_par_jour": h}
                    for m, h in courbe_cuve
                ],
                "regle_par_carburant": [
                    {"multiplicateur": m, "heures_a_sec_par_jour": h}
                    for m, h in courbe_carb
                ],
                "capacite_equivalente": seuil_cuve,
                "m3_de_stockage_evites": (
                    capacite * (seuil_cuve - 1.0) if seuil_cuve else None
                ),
                "carburant_equivalent": seuil_carb,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nécrit dans {SORTIE}")


if __name__ == "__main__":
    main()
