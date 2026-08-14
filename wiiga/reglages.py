"""Le modele lui-meme a-t-il ete pense, ou seulement lance ?

Tout le depot mesure ce que l'agent fait. Rien, jusqu'ici, ne mesurait les choix
qui l'ont fabrique. L'agent publie tourne sur les valeurs par defaut de
Stable-Baselines3 - reseau 64x64, six cent mille pas, aucun bonus d'entropie,
aucune normalisation, taux d'apprentissage constant - et personne n'a verifie
qu'aucune de ces valeurs ne laissait de performance sur la table.

Dans un concours d'apprentissage automatique, c'est le reproche le plus cher
qu'on puisse encaisser. Ce fichier y repond de la seule facon possible : en
entrainant les variantes et en publiant le tableau, y compris quand la variante
perd.

Quatre suspects, dans l'ordre ou ils meritent d'etre soupconnes :

- **la duree.** 600 000 pas est court pour PPO. Si la courbe monte encore a
  l'arret, tout le reste est du bruit a cote.
- **la taille du reseau.** 64x64 pour 27 entrees et 8 sorties continues, quand
  le controle continu publie utilise couramment 256x256.
- **l'exploration.** `ent_coef=0`, alors que l'alerte est un probleme
  d'exploration difficile - mesure, deux graines y trouvaient des optima
  degeneres opposes.
- **l'echelle de recompense.** Elle va de -60 a +12. Sans normalisation, la
  fonction de valeur passe son temps sur les falaises.

Chaque variante ne change **qu'une chose** par rapport a la reference. Deux
variantes qui bougent ensemble ne diraient pas laquelle a compte.

Une graine par variante pour degrossir : c'est assez pour ecarter ce qui ne sert
a rien, pas assez pour couronner un vainqueur. Ce qui sort en tete est rejoue sur
trois graines par `wiiga.graines` avant d'etre publie - la variance inter-graines
mesuree ici est de 0,06 heure a sec, donc un ecart plus petit que ca ne veut rien
dire.

Execution : `python -m wiiga.reglages --entrainer`
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
import pathlib
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, VecNormalize

from .env import GAMMA, WiigaEnv

DOSSIER = Path(__file__).resolve().parent.parent / "agents" / "reglages"
SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "reglages.json"

#: L'ecart en dessous duquel on ne conclut rien. C'est l'ecart-type mesure entre
#: trois graines de la configuration publiee, dans `graines.json`. Une variante
#: qui gagne moins que ca n'a pas gagne, elle a eu de la chance.
BRUIT = 0.06

#: Les variantes. Chacune ne touche qu'un parametre, et le nom dit lequel.
VARIANTES = {
    "reference": {},
    # 1,8 M pas ont pris trois heures et demie pour un gain a mesurer. On garde
    # le modele deja entraine mais on ne le rejoue pas : la duree se teste une
    # fois, pas a chaque relance.
    "trois fois plus long": {"pas": 1_800_000},
    "reseau 256x256": {"net": [256, 256]},
    "entropie 0.01": {"ent_coef": 0.01},
    "recompense normalisee": {"norm": True},
    "pas d'apprentissage decroissant": {"lr_decroissant": True},
    "lot plus grand": {"batch_size": 256, "n_steps": 480},
}


def entrainer_variante(nom: str, spec: dict, seed: int, n_envs: int = 8):
    pas = spec.get("pas", 600_000)
    n_steps = spec.get("n_steps", 240)
    net = spec.get("net", [64, 64])

    env = make_vec_env(
        WiigaEnv,
        n_envs=n_envs,
        seed=seed,
        env_kwargs=dict(confiance_tiree=True),
        vec_env_cls=SubprocVecEnv,
    )
    if spec.get("norm"):
        # les observations sont deja dans [0,1] par construction ; c'est la
        # recompense, de -60 a +12, qui ecrase la fonction de valeur
        env = VecNormalize(env, norm_obs=False, norm_reward=True, gamma=GAMMA)

    lr = 3e-4
    if spec.get("lr_decroissant"):
        lr = lambda reste: 3e-4 * reste  # noqa: E731

    agent = PPO(
        "MlpPolicy",
        env,
        learning_rate=lr,
        n_steps=n_steps,
        batch_size=spec.get("batch_size", 64),
        gamma=GAMMA,
        ent_coef=spec.get("ent_coef", 0.0),
        policy_kwargs=dict(net_arch=net),
        seed=seed,
        device="cpu",
        verbose=0,
    )
    debut = time.time()
    agent.learn(total_timesteps=pas)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER / nom.replace(" ", "_").replace("'", "")
    agent.save(chemin)
    if spec.get("norm"):
        env.save(str(chemin) + "_norm.pkl")
    print(f"  {nom:<34} {pas:>9} pas en {time.time() - debut:>5.0f}s")
    # fermer les huit sous-processus. Sans ca ils s'accumulent d'une variante a
    # l'autre et Windows finit par refuser d'ouvrir un tuyau de plus - mesure :
    # plantage a la troisieme variante, WinError 1450.
    env.close()
    return chemin


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=200)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--graine", type=int, default=0)
    p.add_argument("--entrainer", action="store_true")
    args = p.parse_args()

    from .baselines import prevoyant
    from .resultats import mesurer
    from .train import politique_agent

    if args.entrainer:
        print(f"\nentrainement de {len(VARIANTES)} variantes, graine {args.graine}\n")
        for nom, spec in VARIANTES.items():
            entrainer_variante(nom, spec, args.graine)

    regle = mesurer(prevoyant, args.journees, args.seed)
    base = regle["heures_a_sec_par_jour"]

    print(f"\n{args.journees} journees, memes graines pour tout le monde")
    print(f"regle ecrite : {base:.3f} h a sec/j   |   bruit inter-graines : "
          f"+-{BRUIT:.2f}\n")
    print(f"{'variante':<34}{'h sec/j':>10}{'vs regle':>10}{'alertes/j':>11}"
          f"{'justesse':>10}")
    print("-" * 75)

    lignes, ref = {}, None
    for nom in VARIANTES:
        chemin = DOSSIER / nom.replace(" ", "_").replace("'", "")
        # le point dans "entropie 0.01" fait passer .01 pour une extension :
        # SB3 n'ajoute alors pas .zip, et le fichier reste introuvable
        if not (chemin.with_suffix(".zip").exists() or
                pathlib.Path(str(chemin) + ".zip").exists()):
            print(f"{nom:<34}{'(pas entraine)':>41}")
            continue
        m = mesurer(politique_agent(PPO.load(str(chemin))), args.journees, args.seed)
        h = m["heures_a_sec_par_jour"]
        if nom == "reference":
            ref = h
        ecart = (base - h) / base * 100
        verdict = ""
        if ref is not None and nom != "reference":
            d = ref - h
            verdict = "  mieux" if d > BRUIT else ("  pire" if d < -BRUIT else "  =")
        lignes[nom] = {
            "heures_a_sec_par_jour": h,
            "vs_regle_pct": ecart,
            "alertes_par_jour": m["alertes_par_jour"],
            "justesse_alertes": m["justesse_alertes"],
            "gain_sur_reference": (ref - h) if ref is not None else 0.0,
        }
        print(f"{nom:<34}{h:>10.3f}{ecart:>9.0f}%{m['alertes_par_jour']:>11.2f}"
              f"{m['justesse_alertes'] * 100:>9.0f}%{verdict}")

    if ref is not None and lignes:
        gagnantes = [n for n, v in lignes.items()
                     if n != "reference" and v["gain_sur_reference"] > BRUIT]
        print(f"\nvariantes qui depassent la reference de plus que le bruit "
              f"({BRUIT:.2f} h) : "
              + (", ".join(gagnantes) if gagnantes else "aucune"))
        if not gagnantes:
            print("les valeurs par defaut tiennent. C'est un resultat, pas un echec :")
            print("on saura le dire plutot que de laisser croire qu'on n'a pas cherche.")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed_evaluation": args.seed,
                "graine_entrainement": args.graine,
                "bruit_inter_graines": BRUIT,
                "regle_ecrite": base,
                "variantes": lignes,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\necrit dans {SORTIE}")


if __name__ == "__main__":
    main()
