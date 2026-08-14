"""Produire les chiffres de la soumission, et les écrire pour qu'on les relise.

Un tableau imprimé dans un terminal disparaît. Ce fichier écrit un JSON que le
README, la page de démo et la vidéo lisent tous les trois : il ne peut donc pas
y avoir trois versions du même chiffre.

Trois familles de mesures, parce qu'une seule ment toujours par omission :

- **le service** - heures à sec, jours à sec. Ce que l'habitant subit.
- **le coût** - FCFA, litres de gasoil, kg de CO2. Ce que la régie paie, et ce
  que l'atmosphère paie.
- **le risque** - le creux de la journée, et combien de fois on frôle le vide.
  Une politique qui sert bien en moyenne et se vide une fois par mois n'est pas
  déployable, et la moyenne ne le dit pas.

Exécution : `python -m wiiga.resultats`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .baselines import POLITIQUES
from .demande import PROFILS
from .env import CARBURANT_JOUR, WiigaEnv

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "comparaison.json"

#: Un groupe électrogène diesel rend environ 3,5 kWh par litre de gasoil, et un
#: litre brûlé émet 2,68 kg de CO2. Les deux chiffres sont des ordres de
#: grandeur usuels, pas des mesures faites sur le groupe de la régie - c'est dit
#: ici plutôt que sous-entendu.
KWH_PAR_LITRE = 3.5
CO2_PAR_LITRE = 2.68

#: L'OMS place le besoin de base à 50 L par habitant et par jour, et la survie à
#: 20. Une heure de coupure ne prive pas de 50 L : elle prive de la part horaire
#: de la demande, et c'est ce que compte `litres_manquants`.
LITRES_SURVIE = 20.0


def mesurer(politique, journees: int, seed: int, apres_reset=None) -> dict:
    """Une politique, `journees` journées, et tout ce qu'on sait en compter.

    L'environnement est **neuf pour chaque politique**, et ce n'est pas une
    précaution de style : la crédibilité ne se remet pas à zéro entre deux
    journées, donc un environnement réutilisé ferait démarrer la deuxième
    politique avec la réputation bâtie par la première. Elle verrait une ville
    déjà convaincue dans son observation, et la comparaison mentirait en sa
    faveur.

    `apres_reset` reçoit l'environnement juste après `reset`, avant la première
    décision. C'est le seul point d'entrée pour déformer une journée sans
    réécrire cette boucle : `choc.py` s'en sert pour gonfler la demande d'un
    quartier. Le crochet est ici plutôt que dupliqué là-bas parce que deux
    boucles de mesure finiraient par diverger sur une convention - la graine par
    journée, l'environnement neuf - et par produire deux tableaux qu'on ne
    pourrait plus comparer.
    """
    env = WiigaEnv(seed=0)
    heures_sec, cout, manquants = 0, 0.0, 0.0
    creux, fins, solaire, carburant = [], [], [], 0.0
    jours_sec = 0
    # Le detail par quartier. `heures_a_sec` somme les trois zones : c'est la
    # bonne grandeur pour comparer deux politiques, et c'est la mauvaise pour
    # ecrire « le quartier le plus mal servi reste a sec X heures ». Les deux ont
    # coexiste dans le texte publie, la somme portant le nom du maximum. Elles
    # sont mesurees separement ici pour qu'on ne puisse plus les confondre.
    par_zone: dict[str, int] = {}
    par_saison: dict[str, list] = {}
    alertes = justes = 0
    confiances = []

    for j in range(journees):
        # une journée de l'année par épisode, pour que la moyenne couvre les
        # trois régimes au lieu d'en tirer un au hasard
        env.jour_fixe = j % 365
        obs, _ = env.reset(seed=seed + j)
        if apres_reset is not None:
            # `obs` n'est volontairement pas recalculé : une déformation de la
            # demande réelle ne se voit pas dans l'observation, qui ne porte que
            # la forme normalisée du profil. C'est la propriété que `choc.py`
            # mesure, et la recalculer ici la masquerait.
            apres_reset(env)
        fini = False
        while not fini:
            obs, _, arret, tronque, info = env.step(politique(obs, env))
            fini = arret or tronque

        heures_sec += info["heures_a_sec"]
        for z in env.zones:
            par_zone[z.profil.nom] = par_zone.get(z.profil.nom, 0) + z.heures_a_sec
        jours_sec += 1 if info["heures_a_sec"] > 0 else 0
        cout += info["cout_total"]
        manquants += info["litres_manquants"]
        creux.append(info["creux_journee"])
        fins.append(info["pire_remplissage"])
        solaire.append(info["part_solaire_bue"])
        carburant += CARBURANT_JOUR - info["carburant_restant"]
        par_saison.setdefault(info["saison"], []).append(info["heures_a_sec"])
        confiances.append(info["confiance"])

    # cumulés sur toute la campagne, la crédibilité ne se remettant pas à zéro
    alertes, justes = info["alertes"], info["alertes_justes"]

    creux = np.asarray(creux)
    litres_gasoil = carburant / KWH_PAR_LITRE

    return {
        # service
        #: **La somme des trois quartiers**, pas le pire d'entre eux. Un quartier
        #: a sec une heure et un autre a sec la meme heure comptent deux. C'est ce
        #: qu'il faut pour comparer deux politiques sur toute la ville ; ce n'est
        #: pas ce qu'il faut pour decrire ce que subit un habitant.
        "heures_a_sec_par_jour": heures_sec / journees,
        #: Le detail, et le maximum. La recompense optimise le quartier le plus
        #: mal servi : sans cette ligne, la revendication centrale du projet
        #: n'avait aucune mesure derriere elle.
        "heures_a_sec_par_zone": {n: v / journees for n, v in par_zone.items()},
        "heures_a_sec_pire_zone": (max(par_zone.values()) / journees) if par_zone else 0.0,
        "jours_avec_coupure_sur_200": int(jours_sec * 200 / journees),
        "litres_manquants_par_jour": manquants / journees,
        # ce que ça représente en humain : combien de personnes auraient pu
        # passer la journée au seuil de survie avec l'eau qui a manqué
        "personnes_privees_equivalent_par_jour": manquants / journees / LITRES_SURVIE,
        # coût
        "fcfa_par_jour": cout / journees,
        "litres_gasoil_par_jour": litres_gasoil / journees,
        "kg_co2_par_jour": litres_gasoil * CO2_PAR_LITRE / journees,
        "part_solaire_bue": float(np.mean(solaire)),
        # risque
        "creux_moyen": float(creux.mean()),
        "creux_pire_jour": float(creux.min()),
        "jours_creux_sous_10pct": int((creux < 0.10).sum() * 200 / journees),
        "jours_creux_sous_5pct": int((creux < 0.05).sum() * 200 / journees),
        "remplissage_fin_de_jour": float(np.mean(fins)),
        # par saison : une moyenne annuelle cache que le problème change trois
        # fois de nature, et que les règles écrites s'effondrent en avril
        "heures_a_sec_par_saison": {
            s: float(np.mean(v)) for s, v in sorted(par_saison.items())
        },
        # la parole : combien de fois l'agent a parlé, et s'il avait raison
        "alertes_par_jour": alertes / journees,
        "justesse_alertes": justes / alertes if alertes else 0.0,
        "confiance_finale": float(confiances[-1]) if confiances else 0.0,
    }


def humain(agent: dict, regle: dict, terrain: dict) -> dict:
    """Traduire les mètres cubes en gens, une fois pour toutes.

    Trois conversions, aucune invention. `litres_manquants` est mesuré ; le seuil
    de survie de 20 L par personne et par jour vient de l'OMS ; les 22 000
    habitants sont les paramètres déclarés des trois quartiers dans
    `demande.py`. Le reste est une division.

    Le chiffre à retenir est **personnes-jours** : combien de fois, dans une
    année, quelqu'un est resté sous le seuil de survie qui ne l'aurait pas été.
    C'est la seule unité de ce projet qu'on peut lire sans être ingénieur.
    """
    habitants = sum(p.habitants for p in PROFILS)

    def personnes(m: dict) -> float:
        return m["litres_manquants_par_jour"] / LITRES_SURVIE

    return {
        "habitants_desservis": habitants,
        "personnes_sous_le_seuil_par_jour": {
            "agent": personnes(agent),
            "regle_ecrite": personnes(regle),
            "pratique_actuelle": personnes(terrain),
        },
        # sur une année, contre chacune des deux références
        "personnes_jours_epargnees_par_an_vs_regle": (
            personnes(regle) - personnes(agent)
        )
        * 365.0,
        "personnes_jours_epargnees_par_an_vs_pratique": (
            personnes(terrain) - personnes(agent)
        )
        * 365.0,
        # part de la ville qui subit encore une coupure un jour moyen
        "part_de_la_ville_touchee_agent": personnes(agent) / habitants,
        "part_de_la_ville_touchee_regle": personnes(regle) / habitants,
        # ce que la régie garde en caisse, et ce que l'atmosphère ne reçoit pas
        "fcfa_epargnes_par_an_vs_regle": (
            regle["fcfa_par_jour"] - agent["fcfa_par_jour"]
        )
        * 365.0,
        "kg_co2_evites_par_an_vs_regle": (
            regle["kg_co2_par_jour"] - agent["kg_co2_par_jour"]
        )
        * 365.0,
        # les deux références séparément, parce qu'un pourcentage pris sur l'une
        # et un tonnage pris sur l'autre se lisent comme un seul chiffre et n'en
        # sont pas un : « 48 % de CO2 en moins, 22 tonnes par an » mélangeait la
        # comparaison à la pratique actuelle et celle à la règle écrite.
        "kg_co2_evites_par_an_vs_pratique": (
            terrain["kg_co2_par_jour"] - agent["kg_co2_par_jour"]
        )
        * 365.0,
        "litres_gasoil_evites_par_an_vs_regle": (
            regle["litres_gasoil_par_jour"] - agent["litres_gasoil_par_jour"]
        )
        * 365.0,
    }


def ecart(agent: dict, reference: dict, cle: str) -> float:
    """De combien de pour cent l'agent améliore une mesure où moins vaut mieux."""
    base = reference[cle]
    return 0.0 if base == 0 else (base - agent[cle]) / base * 100.0


def main() -> None:
    from .train import MODELE_PUBLIE

    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=200)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--modele", default=MODELE_PUBLIE)
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .train import politique_agent

    agent = PPO.load(args.modele)
    politiques = dict(POLITIQUES)
    politiques["agent WIIGA (PPO)"] = politique_agent(agent)

    def muet(obs, env):
        """Le même agent, la parole coupée.

        C'est l'ablation qui mesure ce que l'alerte apporte : mêmes poids, même
        journée, même graine, seule la dernière composante de l'action est mise
        à zéro. Comparer deux agents entraînés séparément mélangerait l'effet de
        l'action avec celui de l'entraînement.
        """
        a, _ = agent.predict(obs, deterministic=True)
        a = np.asarray(a, dtype=np.float32).copy()
        a[-1] = 0.0
        return a

    politiques["agent WIIGA, sans la parole"] = muet

    mesures = {
        nom: mesurer(pol, args.journees, args.seed) for nom, pol in politiques.items()
    }

    resultat_agent = mesures["agent WIIGA (PPO)"]
    # la règle écrite est la vraie cible : battre la pratique actuelle est facile,
    # battre quelqu'un qui lit la même prévision que soi ne l'est pas
    regle = mesures["prévoyant (règle écrite)"]
    terrain = mesures["exploitant (consigne fixe)"]
    muet_r = mesures["agent WIIGA, sans la parole"]

    resume = {
        "vs_pratique_actuelle": {
            "heures_a_sec_pct": ecart(resultat_agent, terrain, "heures_a_sec_par_jour"),
            "cout_pct": ecart(resultat_agent, terrain, "fcfa_par_jour"),
            "co2_pct": ecart(resultat_agent, terrain, "kg_co2_par_jour"),
        },
        "vs_regle_ecrite": {
            "heures_a_sec_pct": ecart(resultat_agent, regle, "heures_a_sec_par_jour"),
            "cout_pct": ecart(resultat_agent, regle, "fcfa_par_jour"),
            "co2_pct": ecart(resultat_agent, regle, "kg_co2_par_jour"),
        },
        "vs_lui_meme_sans_la_parole": {
            "heures_a_sec_pct": ecart(resultat_agent, muet_r, "heures_a_sec_par_jour"),
            "cout_pct": ecart(resultat_agent, muet_r, "fcfa_par_jour"),
        },
        # ---------------------------------------------------------- l'humain
        #
        # Un juré ne se représente pas 61 litres de gasoil. Il se représente des
        # gens. Tout ce bloc ne fait que rediviser des grandeurs déjà mesurées
        # par des seuils publics, et c'est écrit ici plutôt que dans le texte de
        # soumission pour qu'on ne puisse pas l'y embellir.
        "en_humain": humain(resultat_agent, regle, terrain),
        "apprentissage_bat_la_regle": (
            resultat_agent["heures_a_sec_par_jour"] <= regle["heures_a_sec_par_jour"]
        ),
        # dit ici pour qu'on ne puisse pas l'oublier dans le write-up
        "reserve_plus_fine_que_la_regle": resultat_agent["creux_moyen"] < regle["creux_moyen"],
    }

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                # quel modèle a produit les tableaux détaillés. Les trois graines
                # vivent dans `graines.json` ; ici il en faut une seule, et on
                # dit laquelle plutôt que de laisser le lecteur le deviner.
                "modele": str(args.modele),
                "mesures": mesures,
                "resume": resume,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    largeur = 30
    print(f"\n{'politique':<{largeur}}{'h sec/j':>9}{'j sec':>7}{'FCFA/j':>9}"
          f"{'L gasoil':>10}{'kg CO2':>9}{'creux':>7}{'<5%':>6}")
    print("-" * (largeur + 57))
    for nom, m in mesures.items():
        print(
            f"{nom:<{largeur}}{m['heures_a_sec_par_jour']:>9.2f}"
            f"{m['jours_avec_coupure_sur_200']:>7}{m['fcfa_par_jour']:>9.0f}"
            f"{m['litres_gasoil_par_jour']:>10.1f}{m['kg_co2_par_jour']:>9.1f}"
            f"{m['creux_moyen']:>7.2f}{m['jours_creux_sous_5pct']:>6}"
        )

    # les saisons séparément : la moyenne annuelle cache que la règle écrite
    # s'effondre à un moment précis de l'année, et c'est ce moment qui compte
    saisons = sorted(resultat_agent["heures_a_sec_par_saison"])
    print(f"\n{'heures à sec / jour, par saison':<{largeur}}"
          + "".join(f"{s:>16}" for s in saisons))
    print("-" * (largeur + 16 * len(saisons)))
    for nom, m in mesures.items():
        print(f"{nom:<{largeur}}"
              + "".join(f"{m['heures_a_sec_par_saison'][s]:>16.2f}" for s in saisons))

    print(f"\n{'la parole':<{largeur}}{'alertes/j':>11}{'justesse':>10}{'confiance':>11}")
    print("-" * (largeur + 32))
    for nom, m in mesures.items():
        print(f"{nom:<{largeur}}{m['alertes_par_jour']:>11.2f}"
              f"{m['justesse_alertes'] * 100:>9.0f}%{m['confiance_finale']:>11.2f}")

    print(f"\nvs pratique actuelle : "
          f"{resume['vs_pratique_actuelle']['heures_a_sec_pct']:.0f}% d'heures à sec en moins, "
          f"{resume['vs_pratique_actuelle']['cout_pct']:.0f}% moins cher")
    if terrain["litres_gasoil_par_jour"] < 1.0:
        # à ne surtout pas présenter comme « 0 % de CO2 en moins » : la consigne
        # fixe ne brûle rien parce qu'elle ne pompe pas quand le réseau tombe.
        # Son bilan carbone est nul et son bilan humain est de 122 jours de
        # coupure sur 200. La comparaison n'a de sens que contre les règles.
        print(f"                       (la consigne fixe ne brûle aucun gasoil : elle "
              f"ne pompe pas quand le réseau tombe, et laisse "
              f"{terrain['jours_avec_coupure_sur_200']} jours à sec sur 200)")
    print(f"vs règle écrite      : "
          f"{resume['vs_regle_ecrite']['heures_a_sec_pct']:.0f}% d'heures à sec en moins, "
          f"{resume['vs_regle_ecrite']['cout_pct']:.0f}% moins cher, "
          f"{resume['vs_regle_ecrite']['co2_pct']:.0f}% de CO2 en moins")
    print(f"vs lui-même, muet    : "
          f"{resume['vs_lui_meme_sans_la_parole']['heures_a_sec_pct']:.0f}% d'heures à sec "
          f"en moins, {resume['vs_lui_meme_sans_la_parole']['cout_pct']:.0f}% moins cher "
          f"- mêmes poids, seule l'alerte diffère")
    if not resume["reserve_plus_fine_que_la_regle"]:
        print("l'agent garde autant de réserve que la règle")
    else:
        print(f"réserve plus fine que la règle : creux {resultat_agent['creux_moyen']:.2f} "
              f"contre {regle['creux_moyen']:.2f} - à dire tel quel")
    h = resume["en_humain"]
    print(f"\n{'en gens plutôt qu\'en mètres cubes':<40}")
    print("-" * 62)
    print(f"  {h['habitants_desservis']:,} habitants sur trois quartiers".replace(",", " "))
    print(f"  sous le seuil de survie OMS un jour moyen : "
          f"{h['personnes_sous_le_seuil_par_jour']['agent']:.0f} personnes avec "
          f"l'agent, {h['personnes_sous_le_seuil_par_jour']['regle_ecrite']:.0f} "
          f"avec la règle écrite")
    print(f"  soit {h['personnes_jours_epargnees_par_an_vs_regle']:,.0f} "
          f"personnes-jours épargnées par an".replace(",", " "))
    print(f"  et {h['personnes_jours_epargnees_par_an_vs_pratique']:,.0f} "
          f"contre la pratique actuelle".replace(",", " "))
    print(f"  {h['kg_co2_evites_par_an_vs_regle']:,.0f} kg de CO2 et "
          f"{h['fcfa_epargnes_par_an_vs_regle']:,.0f} FCFA par an".replace(",", " "))

    print(f"\nécrit dans {SORTIE}")


if __name__ == "__main__":
    main()
