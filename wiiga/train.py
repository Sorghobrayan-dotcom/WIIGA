"""Entraîner l'agent, et le comparer honnêtement à ce qui ne s'entraîne pas.

Le point de comparaison qui compte n'est pas le hasard, c'est `prévoyant` : une
règle de vingt lignes qui lit la même prévision de coupure que l'agent. Si PPO
ne la bat pas, l'apprentissage ne sert à rien ici et il faut l'écrire plutôt que
de publier une courbe de récompense qui monte.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import SubprocVecEnv

from .baselines import POLITIQUES, evaluer
from .env import GAMMA, WiigaEnv

MODELE = Path(__file__).parent.parent / "wiiga_agent"


#: Combien d'environnements tournent en parallèle.
#:
#: C'est le seul levier de vitesse qui compte ici, et il n'a rien à voir avec le
#: GPU. Le réseau de politique fait deux couches de 64 sur 27 entrées : quelques
#: microsecondes, dominées par le coût de lancement d'un noyau CUDA. Ce qui prend
#: le temps, c'est **l'environnement**, une boucle Python à environ 5 000 pas par
#: seconde sur un cœur. Un GPU n'accélère pas une boucle Python ; des cœurs, si.
#:
#: Huit plutôt que quatorze : au-delà, la collecte de trajectoires ne domine plus
#: et la phase de mise à jour, elle, reste séquentielle.
ENVIRONNEMENTS = 8


def entrainer(
    pas: int = 150_000,
    seed: int = 0,
    verbose: int = 0,
    sortie: Path | None = None,
    equite: bool = True,
    n_envs: int = ENVIRONNEMENTS,
) -> PPO:
    # `confiance_tiree` uniquement ici : à l'entraînement l'agent doit rencontrer
    # toute la gamme de crédibilité, sans quoi il détruit le canal d'alerte dans
    # ses vingt premières journées et n'apprend jamais à s'en servir. À la
    # mesure, la confiance persiste — c'est le vrai déploiement.
    reglages = dict(confiance_tiree=True, equite=equite)
    if n_envs > 1:
        env = make_vec_env(
            WiigaEnv,
            n_envs=n_envs,
            seed=seed,
            env_kwargs=reglages,
            vec_env_cls=SubprocVecEnv,
        )
    else:
        env = Monitor(WiigaEnv(seed=seed, **reglages))

    agent = PPO(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        # par environnement : huit fois 256 refont les 2 048 pas de rollout
        # d'origine, pour que le nombre de mises à jour ne dépende pas du nombre
        # de cœurs de la machine qui entraîne
        n_steps=max(64, 2048 // n_envs),
        batch_size=64,
        # une journée fait 24 pas : inutile d'escompter sur mille. Importé plutôt
        # que réécrit, l'environnement s'en servant aussi pour raisonner sur son
        # horizon — deux valeurs qui divergeraient seraient invisibles.
        gamma=GAMMA,
        verbose=verbose,
        seed=seed,
        # explicite : sur ce réseau, le CPU bat le GPU, et un choix silencieux
        # serait un choix qu'on ne peut pas discuter
        device="cpu",
    )
    debut = time.time()
    agent.learn(total_timesteps=pas)
    cible = sortie or MODELE
    agent.save(cible)
    print(f"agent entraîné en {time.time() - debut:.0f}s, sauvegardé dans {cible.name}")
    return agent


def politique_agent(agent: PPO):
    """Emballer l'agent pour qu'il s'évalue comme n'importe quelle règle."""

    def jouer(obs, env):
        action, _ = agent.predict(obs, deterministic=True)
        return action

    return jouer


def comparer(agent: PPO, journees: int = 200, seed: int = 1000) -> None:
    # un environnement neuf par politique : la crédibilité auprès de la ville
    # survit au `reset`, donc un environnement partagé ferait hériter la seconde
    # politique de la réputation bâtie par la première
    politiques = dict(POLITIQUES)
    politiques["agent WIIGA (PPO)"] = politique_agent(agent)
    lignes = [
        (nom, evaluer(pol, WiigaEnv(seed=0), journees, seed))
        for nom, pol in politiques.items()
    ]

    print()
    print(f"{'politique':<30}{'h à sec/j':>11}{'FCFA/j':>10}{'pire':>7}{'mains':>8}")
    print("-" * 66)
    for nom, r in lignes:
        print(
            f"{nom:<30}{r['heures à sec / jour']:>11.2f}"
            f"{r['coût / jour (FCFA)']:>10.0f}{r['pire remplissage moyen']:>7.2f}"
            f"{r['mains rendues / jour']:>8.1f}"
        )

    regle = dict(lignes)["prévoyant (règle écrite)"]
    ppo = dict(lignes)["agent WIIGA (PPO)"]
    mieux = ppo["heures à sec / jour"] <= regle["heures à sec / jour"]
    print()
    print(
        "l'apprentissage bat la règle écrite à la main"
        if mieux
        else "la règle écrite bat l'apprentissage — à dire tel quel"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pas", type=int, default=150_000)
    p.add_argument("--journees", type=int, default=200)
    p.add_argument("--graine", type=int, default=0)
    p.add_argument("--sortie", default=None)
    p.add_argument("--envs", type=int, default=ENVIRONNEMENTS)
    args = p.parse_args()

    sortie = Path(args.sortie) if args.sortie else None
    comparer(
        entrainer(args.pas, seed=args.graine, sortie=sortie, n_envs=args.envs),
        journees=args.journees,
    )
