"""Le même agent, entraîné plusieurs fois. Est-ce que le résultat tient ?

C'est la question qu'un lecteur qui connaît l'apprentissage par renforcement pose
en premier, et c'est l'attaque la plus crédible contre n'importe quel chiffre de
ce dépôt : **PPO est stochastique, et un écart de 38 % obtenu sur une seule
graine peut n'être qu'une bonne pioche.**

Trois entraînements complets, trois graines différentes, évalués sur les mêmes
365 journées et les mêmes graines d'évaluation que les règles écrites. On publie
la moyenne, l'écart-type, et surtout **le pire des trois** — parce que c'est lui
qui dit ce qu'on obtient quand on n'a pas de chance.

Un résultat qui ne survit pas à sa propre variance n'est pas un résultat. Si les
trois graines ne battent pas la règle écrite, il faut l'écrire.

Entraîner puis mesurer :

    python -m wiiga.graines --entrainer --pas 600000
    python -m wiiga.graines --journees 365
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .baselines import POLITIQUES
from .resultats import mesurer

DOSSIER = Path(__file__).resolve().parent.parent / "agents"
SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "graines.json"

#: Les mesures qu'on regarde d'une graine à l'autre. Trois familles, pour ne pas
#: pouvoir choisir après coup celle qui arrange.
CLES = (
    ("heures_a_sec_par_jour", "heures à sec / jour", 2),
    ("personnes_privees_equivalent_par_jour", "personnes sous le seuil", 0),
    ("fcfa_par_jour", "FCFA / jour", 0),
    ("kg_co2_par_jour", "kg CO2 / jour", 1),
    ("creux_moyen", "creux moyen", 2),
    ("alertes_par_jour", "alertes / jour", 2),
    ("justesse_alertes", "justesse des alertes", 2),
)


def modeles() -> list[Path]:
    return sorted(DOSSIER.glob("graine_*.zip"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=365)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--graines", type=int, default=3)
    p.add_argument("--pas", type=int, default=600_000)
    p.add_argument("--entrainer", action="store_true")
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .train import entrainer, politique_agent

    if args.entrainer:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        for g in range(args.graines):
            entrainer(args.pas, seed=g, sortie=DOSSIER / f"graine_{g}")

    chemins = modeles()
    if not chemins:
        raise SystemExit(
            f"aucun modèle dans {DOSSIER} — lancer d'abord `--entrainer`"
        )

    # les règles d'abord : elles ne dépendent d'aucune graine d'entraînement, et
    # ce sont elles qui donnent le sens des écarts
    regles = {
        nom: mesurer(pol, args.journees, args.seed) for nom, pol in POLITIQUES.items()
    }
    regle = regles["prévoyant (règle écrite)"]

    par_graine = {}
    for chemin in chemins:
        agent = politique_agent(PPO.load(chemin))
        par_graine[chemin.stem] = mesurer(agent, args.journees, args.seed)

    stats = {}
    for cle, _, _ in CLES:
        v = np.array([m[cle] for m in par_graine.values()])
        stats[cle] = {
            "moyenne": float(v.mean()),
            "ecart_type": float(v.std(ddof=1)) if v.size > 1 else 0.0,
            "min": float(v.min()),
            "max": float(v.max()),
        }

    # l'écart à la règle, graine par graine : c'est le chiffre du dossier, et on
    # veut savoir combien il bouge et si le plus mauvais tient encore
    ecarts = np.array(
        [
            (regle["heures_a_sec_par_jour"] - m["heures_a_sec_par_jour"])
            / regle["heures_a_sec_par_jour"]
            * 100.0
            for m in par_graine.values()
        ]
    )
    toutes_gagnent = bool(
        all(
            m["heures_a_sec_par_jour"] <= regle["heures_a_sec_par_jour"]
            for m in par_graine.values()
        )
    )

    largeur = 26
    print(f"\n{len(chemins)} graines d'entraînement, {args.journees} journées, "
          f"graines d'évaluation identiques\n")
    print(f"{'mesure':<{largeur}}" + "".join(f"{c.stem:>13}" for c in chemins)
          + f"{'moyenne':>11}{'ecart-t':>9}{'regle':>11}")
    print("-" * (largeur + 13 * len(chemins) + 31))
    for cle, titre, dec in CLES:
        ligne = f"{titre:<{largeur}}"
        for m in par_graine.values():
            ligne += f"{m[cle]:>13.{dec}f}"
        ligne += f"{stats[cle]['moyenne']:>11.{dec}f}{stats[cle]['ecart_type']:>9.{dec}f}"
        ligne += f"{regle[cle]:>11.{dec}f}" if cle in regle else f"{'—':>11}"
        print(ligne)

    print(f"\nécart à la règle écrite, heures à sec : "
          f"{ecarts.mean():.0f} % en moyenne, "
          f"de {ecarts.min():.0f} % à {ecarts.max():.0f} % selon la graine")
    print(
        "les trois graines battent la règle écrite"
        if toutes_gagnent
        else "au moins une graine perd contre la règle écrite — à dire tel quel"
    )

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed_evaluation": args.seed,
                "graines": {k: v for k, v in par_graine.items()},
                "statistiques": stats,
                "regles": regles,
                "ecart_a_la_regle_pct": {
                    "moyenne": float(ecarts.mean()),
                    "min": float(ecarts.min()),
                    "max": float(ecarts.max()),
                    "ecart_type": float(ecarts.std(ddof=1)) if ecarts.size > 1 else 0.0,
                },
                "toutes_les_graines_battent_la_regle": toutes_gagnent,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nécrit dans {SORTIE}")


if __name__ == "__main__":
    main()
