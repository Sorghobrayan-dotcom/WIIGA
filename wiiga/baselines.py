"""Contre quoi l'agent doit gagner.

Un agent entraîné qui bat le hasard ne prouve rien. Ce qu'il faut battre, c'est
ce que fait l'exploitant aujourd'hui, et ce que ferait la formulation habituelle
du problème. Les deux sont ici, et le second est le plus important : c'est lui
qui montre que les trois écarts de `env.py` servent à quelque chose plutôt qu'à
paraître originaux.
"""

from __future__ import annotations

import numpy as np

from .env import HORIZON_RESEAU, SOURCES, WiigaEnv, consigne_exploitant, solaire_horaire


def _action(puissances, sources, passer_la_main=False, alerter=False) -> np.ndarray:
    """Assembler le vecteur d'action attendu par l'environnement.

    Aucune règle n'alerte jamais, et c'est le point : prévenir la ville demande
    de prédire la coupure, pas de réagir à l'heure qu'il est. Les règles écrites
    ne savent pas le faire, et c'est ce que l'agent doit gagner.
    """
    a = []
    for p, s in zip(puissances, sources):
        a.append(float(np.clip(p, 0, 1)))
        # le centre de la tranche, pour ne pas dépendre de l'arrondi
        a.append((SOURCES.index(s) + 0.5) / 3.0)
    a.append(1.0 if passer_la_main else 0.0)
    a.append(1.0 if alerter else 0.0)
    return np.array(a, dtype=np.float32)


def exploitant(obs: np.ndarray, env: WiigaEnv) -> np.ndarray:
    """La consigne fixe : à fond la nuit, au ralenti le jour, toujours réseau.

    C'est ce qui tourne réellement, et c'est le seuil au-dessus duquel le projet
    a une raison d'exister.
    """
    puissances = consigne_exploitant(env.heure, env.n_zones)
    return _action(puissances, ["reseau"] * env.n_zones)


def moins_cher(obs: np.ndarray, env: WiigaEnv) -> np.ndarray:
    """La formulation habituelle : prendre la source disponible la moins chère.

    Gratuit au soleil, sinon réseau, sinon groupe. Elle ne regarde jamais devant
    elle, donc elle se fait prendre par le délestage exactement comme un
    exploitant sans prévision - et c'est le point.
    """
    heure = env.heure
    soleil = solaire_horaire(heure)
    reseau_up = env.reseau.disponible(heure)

    if soleil > 0.2:
        source = "solaire"
    elif reseau_up:
        source = "reseau"
    else:
        source = "diesel"

    # pomper seulement ce qui manque, cuve par cuve
    puissances = [float(np.clip(1.0 - z.remplissage, 0.15, 1.0)) for z in env.zones]
    return _action(puissances, [source] * env.n_zones)


def prevoyant(obs: np.ndarray, env: WiigaEnv) -> np.ndarray:
    """Une règle écrite à la main qui, elle, regarde la prévision.

    Pas un agent : une heuristique. Elle existe pour répondre à l'objection
    honnête « votre apprentissage n'apporte rien qu'un `if` ne ferait ». Si le
    PPO ne la bat pas, il faut le dire.
    """
    heure = env.heure
    soleil = solaire_horaire(heure)
    reseau_up = env.reseau.disponible(heure)
    risque = float(env.reseau.prevision(heure, HORIZON_RESEAU).max())

    # une coupure se prépare : remplir maintenant, quel qu'en soit le prix
    urgence = risque > 0.45

    if soleil > 0.2:
        source = "solaire"
    elif reseau_up:
        source = "reseau"
    else:
        source = "diesel"

    puissances = []
    for z in env.zones:
        manque = 1.0 - z.remplissage
        puissances.append(float(np.clip(manque * (1.8 if urgence else 1.0), 0.1, 1.0)))
    return _action(puissances, [source] * env.n_zones)


POLITIQUES = {
    "exploitant (consigne fixe)": exploitant,
    "moins cher (sans prévision)": moins_cher,
    "prévoyant (règle écrite)": prevoyant,
}


def evaluer(politique, env: WiigaEnv, journees: int = 200, seed: int = 0) -> dict:
    """Faire tourner une politique sur `journees` journées et compter ce qui compte.

    Ce qui compte n'est pas la récompense - elle dépend de la façon dont on l'a
    écrite. Ce sont les heures pendant lesquelles un quartier n'a pas eu d'eau,
    et les francs dépensés.
    """
    a_sec, cout, pire, rendues, total = 0, 0.0, [], 0, 0.0
    solaire, manquants, creux = [], 0.0, []

    for j in range(journees):
        obs, _ = env.reset(seed=seed + j)
        fini = False
        while not fini:
            action = politique(obs, env)
            obs, r, arret, tronque, info = env.step(action)
            fini = arret or tronque
            total += r
        a_sec += info["heures_a_sec"]
        cout += info["cout_total"]
        pire.append(info["pire_remplissage"])
        rendues += info["mains_rendues"]
        solaire.append(info["part_solaire_bue"])
        manquants += info["litres_manquants"]
        creux.append(info["creux_journee"])

    return {
        "heures à sec / jour": a_sec / journees,
        "coût / jour (FCFA)": cout / journees,
        "pire remplissage moyen": float(np.mean(pire)),
        #: la marge au pire moment de la journée, moyennée sur les journées, et
        #: le pire jour de tous - c'est celui-là qu'un exploitant regarde
        "creux moyen": float(np.mean(creux)),
        "creux du pire jour": float(np.min(creux)),
        "mains rendues / jour": rendues / journees,
        "récompense / jour": total / journees,
        # le chiffre de la batterie virtuelle : l'eau bue qui vient du soleil
        "part solaire bue": float(np.mean(solaire)),
        "litres manquants / jour": manquants / journees,
    }
