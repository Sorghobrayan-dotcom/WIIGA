"""A quoi ressemble vraiment le signal que la regle ecrite doit trancher.

Le README affirme qu'aucun seuil ne peut faire ce travail, et l'argument ne
repose pas sur le fait que notre seuil est mal choisi : il repose sur la forme du
signal. La prevision de coupure a quatre heures est **bimodale**. Elle vaut
presque zero quand rien ne vient, elle est haute quand quelque chose vient, et
elle n'occupe presque jamais le milieu - or c'est le milieu qu'un seuil arbitre.
Deplacer le seuil ne change alors presque rien, parce qu'il n'y a presque pas de
masse de probabilite entre les deux modes.

C'est une affirmation sur une distribution, donc elle se mesure. Elle etait
ecrite dans le README avec ses trois chiffres et aucune commande derriere :
`wiiga.meilleure_regle` montrait que la grille est plate, sans jamais montrer
**pourquoi** elle l'est. Ce module montre le pourquoi.

Les journees sont tirees exactement comme celles de `resultats.mesurer` : meme
environnement, meme `jour_fixe`, meme graine par journee. La distribution decrite
ici est donc celle des journees sur lesquelles la regle a ete notee, et pas une
autre annee tiree pour l'occasion.

La grandeur mesuree est celle que la regle lit, ligne pour ligne :
`env.reseau.prevision(heure, HORIZON_RESEAU).max()` - le risque annonce le plus
fort des quatre prochaines heures.

Execution : `python -m wiiga.prevision`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .calendrier import OUAGADOUGOU, journee
from .env import HORIZON_RESEAU, WiigaEnv

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "prevision.json"

#: Les seuils que le README compare. Ce sont deux valeurs de la grille de
#: `meilleure_regle`, prises aux deux bouts de la plage raisonnable.
SEUILS_COMPARES = (0.15, 0.60)

#: Les bornes de la zone mediane. Un seuil ne peut trancher que ce qui tombe
#: entre les deux : ce qui est en dessous est declare calme par tous les seuils,
#: ce qui est au-dessus est declare urgent par tous.
ZONE_GRISE = (0.20, 0.50)


def risques_de_l_annee(journees: int, seed: int) -> tuple[np.ndarray, list[str]]:
    """Les 24 risques annonces de chaque journee, et la saison de chacune."""
    env = WiigaEnv(seed=0)
    risques, saisons = [], []
    for j in range(journees):
        env.jour_fixe = j % 365
        env.reset(seed=seed + j)
        saison = journee(j % 365, OUAGADOUGOU).saison
        for h in range(24):
            risques.append(float(env.reseau.prevision(h, HORIZON_RESEAU).max()))
            saisons.append(saison)
    return np.asarray(risques), saisons


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=365)
    p.add_argument("--seed", type=int, default=1000)
    args = p.parse_args()

    risques, saisons = risques_de_l_annee(args.journees, args.seed)
    saisons = np.asarray(saisons)

    par_saison = {
        s: float(np.median(risques[saisons == s])) for s in sorted(set(saisons))
    }
    bas, haut = ZONE_GRISE
    au_milieu = float(((risques > bas) & (risques < haut)).mean())
    s0, s1 = SEUILS_COMPARES
    urgences = {s: float((risques > s).mean()) for s in SEUILS_COMPARES}
    ecart_seuils = abs(urgences[s0] - urgences[s1])

    print(f"\n{len(risques)} heures de prevision, {args.journees} journees, "
          f"graines {args.seed} a {args.seed + args.journees - 1}")
    print(f"  mediane sur l'annee              : {np.median(risques):.3f}")
    for s, v in par_saison.items():
        print(f"  mediane en saison {s:<15}: {v:.3f}")
    print(f"\n  entre {bas} et {haut} - la zone qu'un seuil arbitre : "
          f"{au_milieu * 100:.1f} % des heures")
    print(f"  urgence declaree au seuil {s0}      : {urgences[s0] * 100:.1f} % des heures")
    print(f"  urgence declaree au seuil {s1}      : {urgences[s1] * 100:.1f} % des heures")
    print(f"  soit {ecart_seuils * 100:.1f} points d'ecart pour un seuil "
          f"multiplie par {s1 / s0:.0f}")

    bornes = np.linspace(0.0, 1.0, 11)
    parts = np.histogram(risques, bins=bornes)[0] / len(risques)
    print("\ndistribution du risque annonce")
    for i, part in enumerate(parts):
        barre = "#" * int(round(part * 60))
        print(f"  {bornes[i]:.1f}-{bornes[i + 1]:.1f} {part * 100:>5.1f} % {barre}")
    print("\nDeux modes, presque rien entre les deux : c'est la forme du signal,")
    print("pas le reglage du seuil, qui empeche une regle scalaire de trancher.")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                "heures_mesurees": len(risques),
                "horizon_heures": HORIZON_RESEAU,
                "mediane_annee": float(np.median(risques)),
                "mediane_par_saison": par_saison,
                "zone_grise": {"bas": bas, "haut": haut, "part": au_milieu},
                "part_urgence_par_seuil": {str(s): v for s, v in urgences.items()},
                "ecart_entre_les_deux_seuils_points": ecart_seuils * 100,
                "histogramme": {
                    f"{bornes[i]:.1f}-{bornes[i + 1]:.1f}": float(parts[i])
                    for i in range(len(parts))
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\necrit dans {SORTIE}")


if __name__ == "__main__":
    main()
