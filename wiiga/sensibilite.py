"""Les constantes posées à la main changent-elles la conclusion ?

Trois valeurs de ce simulateur ne viennent d'aucune mesure de terrain. Elles ont
été choisies pour que le problème existe, et une lecture honnête peut soupçonner
qu'elles ont été choisies pour que l'agent gagne. C'est le reproche le plus
sérieux qu'on puisse faire à ce dépôt, et la seule réponse valable est un
balayage.

- **`CARBURANT_JOUR`** - les kWh de groupe électrogène disponibles par jour. À
  320, c'est 91 litres de gasoil, 14 % de l'énergie nécessaire pour pomper une
  journée moyenne, un fût de 200 litres tous les deux jours, et de quoi tenir
  1,8 heure de pointe. Plausible pour une régie de quartier - mais posé.
- **`MARGE_POMPE`** - le surdimensionnement des pompes par rapport au pic de
  leur quartier. En dessous de 1, aucune politique ne peut servir la ville et le
  banc d'essai ne mesure plus rien.

`RESERVE_MINIMALE` a été balayée puis retirée, et l'erreur mérite d'être écrite :
cette constante n'existe que dans la **récompense**. La faire varier au moment de
la mesure ne change strictement rien, puisque l'agent est déjà entraîné et que la
règle écrite ne lit aucune récompense - les cinq lignes sortaient identiques au
centième. La balayer honnêtement demanderait un réentraînement par valeur, soit
une heure de calcul par point ; tant que ce n'est pas fait, on ne prétend rien
sur elle.

Ce qu'on cherche n'est pas que les chiffres restent identiques - ils bougeront,
et c'est normal : on change le problème. Ce qu'on cherche est de savoir **si
l'agent bat toujours la règle écrite quand on déplace ces valeurs**. Si oui, la
conclusion ne tient pas au réglage. Si non, il faut le dire à cet endroit précis
plutôt que de laisser quelqu'un le découvrir.

Exécution : `python -m wiiga.sensibilite`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from . import env as menv
from . import resultats as mres
from .baselines import prevoyant
from .resultats import mesurer

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "sensibilite.json"

#: Ce qu'on fait varier, et sur quelle plage. Les plages ne sont pas symétriques
#: autour de la valeur retenue : elles vont là où la valeur cesse d'être
#: plausible, ce qui est le seul intervalle intéressant.
BALAYAGES = {
    "CARBURANT_JOUR": {
        "valeurs": (80.0, 160.0, 320.0, 640.0, 1280.0),
        "unite": "kWh de groupe par jour",
        "lecture": lambda v: f"{v / 3.5:.0f} L de gasoil, "
        f"{v / 2257 * 100:.0f} % de l'énergie du jour",
    },
    "MARGE_POMPE": {
        "valeurs": (1.5, 2.0, 2.5, 3.0, 4.0),
        "unite": "surdimensionnement des pompes",
        "lecture": lambda v: f"{v:.1f}x le pic horaire du quartier",
    },
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=120)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--modele", default="agents/graine_0")
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .train import politique_agent

    agent = politique_agent(PPO.load(args.modele))
    resultats: dict[str, list] = {}
    tient_partout = True

    for nom, spec in BALAYAGES.items():
        origine = getattr(menv, nom)
        lignes = []
        print(f"\n{nom} - {spec['unite']}   (retenu : {origine})")
        print(f"{'valeur':>10}{'agent':>9}{'règle':>9}{'écart':>9}   ce que ça veut dire")
        print("-" * 78)

        for v in spec["valeurs"]:
            setattr(menv, nom, v)
            # `resultats` a importé la constante par valeur pour compter le
            # gasoil ; sans cette ligne son comptage resterait sur l'ancienne et
            # le JSON contiendrait un chiffre faux à côté d'un chiffre juste
            if nom == "CARBURANT_JOUR":
                mres.CARBURANT_JOUR = v
            a = mesurer(agent, args.journees, args.seed)
            r = mesurer(prevoyant, args.journees, args.seed)
            base = r["heures_a_sec_par_jour"]
            ecart = 0.0 if base == 0 else (base - a["heures_a_sec_par_jour"]) / base * 100
            gagne = a["heures_a_sec_par_jour"] <= base
            tient_partout = tient_partout and gagne
            marque = "" if gagne else "   <- la règle gagne"
            lignes.append(
                {
                    "valeur": v,
                    "retenue": v == origine,
                    "agent_heures_a_sec": a["heures_a_sec_par_jour"],
                    "regle_heures_a_sec": base,
                    "ecart_pct": ecart,
                    "agent_gagne": gagne,
                }
            )
            etoile = " *" if v == origine else "  "
            print(f"{v:>9}{etoile}{a['heures_a_sec_par_jour']:>9.2f}{base:>9.2f}"
                  f"{ecart:>8.0f}%   {spec['lecture'](v)}{marque}")

        setattr(menv, nom, origine)
        if nom == "CARBURANT_JOUR":
            mres.CARBURANT_JOUR = origine
        resultats[nom] = lignes

    print("\n* = la valeur retenue dans le dépôt")
    print(
        "\nl'agent bat la règle écrite sur TOUTE la plage des trois constantes"
        if tient_partout
        else "\nla règle gagne quelque part - les lignes marquées ci-dessus"
    )

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                "modele": args.modele,
                "balayages": resultats,
                "conclusion_robuste": tient_partout,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nécrit dans {SORTIE}")


if __name__ == "__main__":
    main()
