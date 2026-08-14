"""Optimiser les pires journees, pas la journee moyenne.

La recompense de `env.py` est deja rawlsienne dans l'espace : elle lit le
quartier le plus mal servi, jamais la moyenne des trois. Assecher un quartier
pour en garder deux pleins est excellent en moyenne et inacceptable, et cette
ligne-la porte tout le projet.

Mais elle reste esperee dans le **temps**. PPO maximise le retour moyen sur la
distribution des journees, donc une politique qui sert parfaitement onze mois et
laisse la ville a sec trois jours en avril peut battre une politique reguliere.
Une regie n'est pas jugee sur sa journee moyenne. Elle est jugee sur sa pire
semaine - c'est celle dont les gens se souviennent, celle qui passe a la radio,
celle qui fait descendre les gens dans la rue.

Ce fichier applique le meme principe au second axe : **on optimise la CVaR**, la
moyenne conditionnelle des `ALPHA` pour cent de journees les pires, au lieu de
l'esperance. Rawlsien dans l'espace *et* dans le temps.

**Comment.** Apres chaque collecte, on calcule le retour de chaque journee du
lot, on garde les pires, et on met a zero l'avantage de toutes les autres. Le
gradient ne voit plus que la queue de la distribution. C'est la variante par
troncature de la CVaR : plus grossiere qu'une formulation duale a la
Rockafellar-Uryasev, et assez pour deplacer la politique - ce qu'on verifie
plutot que de le supposer.

**Ce qu'on attend, et qu'il faut annoncer avant de mesurer :** cet agent doit
etre *moins bon en moyenne* que l'agent standard. S'il etait meilleur partout,
c'est que la CVaR ne changerait rien et qu'on aurait ajoute de la complexite pour
rien. Le resultat qu'on cherche est un echange : un peu de moyenne contre
beaucoup de queue. On publie les deux colonnes.

Entrainement : `python -m wiiga.risque --entrainer --pas 600000`
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv

from .env import GAMMA, HEURES, WiigaEnv

DOSSIER = Path(__file__).resolve().parent.parent / "agents"
SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "risque.json"

#: La part de journees les pires sur laquelle on optimise. 0,20 plutot que 0,05 :
#: en dessous, il reste trop peu de journees par lot pour que le gradient soit
#: autre chose que du bruit - avec 80 journees collectees, 5 % en laisserait
#: quatre. C'est le compromis entre la purete de la CVaR et le fait d'avoir
#: quelque chose a apprendre.
ALPHA = 0.20

#: Multiple de 24 pour que les journees tombent juste dans le tampon : sans ca,
#: une journee est coupee en deux entre deux collectes et son retour ne veut
#: plus rien dire.
PAS_PAR_ENV = 240


class PPOQueue(PPO):
    """PPO qui n'apprend que des pires journees de chaque lot.

    Une seule methode change. Avant la mise a jour, on decoupe le tampon en
    journees, on classe leurs retours, et on annule l'avantage de celles qui vont
    bien. Le reste de l'algorithme est celui de Stable-Baselines3, sans
    modification : ce qu'on revendique est un changement d'objectif, pas une
    nouvelle methode d'optimisation, et melanger les deux rendrait le resultat
    ininterpretable.
    """

    def __init__(self, *args, alpha: float = ALPHA, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.alpha = alpha
        #: pour pouvoir dire, apres coup, sur quelle part du lot on a appris
        self.part_gardee: list[float] = []

    def train(self) -> None:
        a = self.rollout_buffer.advantages  # (n_steps, n_envs)
        n_steps, n_envs = a.shape
        journees = n_steps // HEURES

        if journees >= 5:
            r = self.rollout_buffer.rewards.reshape(journees, HEURES, n_envs)
            #: le retour non escompte de chaque journee : c'est ce qu'un
            #: exploitant regarde en fin de journee, pas une somme ponderee
            retours = r.sum(axis=1).reshape(-1)  # (journees * n_envs,)
            garder = max(1, int(np.ceil(self.alpha * retours.size)))
            seuil = np.partition(retours, garder - 1)[garder - 1]
            masque = (retours <= seuil).reshape(journees, 1, n_envs)
            masque = np.repeat(masque, HEURES, axis=1).reshape(n_steps, n_envs)

            a *= masque
            # renormaliser sur ce qui reste, sinon la taille du pas s'effondre
            # simplement parce qu'on a mis 80 % du lot a zero
            gardes = a[masque]
            if gardes.size > 1 and gardes.std() > 1e-8:
                a[masque] = (gardes - gardes.mean()) / (gardes.std() + 1e-8)
            self.part_gardee.append(float(masque.mean()))

        super().train()


def entrainer(pas: int, seed: int, sortie: Path, n_envs: int = 8) -> PPOQueue:
    env = make_vec_env(
        WiigaEnv,
        n_envs=n_envs,
        seed=seed,
        env_kwargs=dict(confiance_tiree=True),
        vec_env_cls=SubprocVecEnv,
    )
    agent = PPOQueue(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        n_steps=PAS_PAR_ENV,
        batch_size=64,
        gamma=GAMMA,
        seed=seed,
        device="cpu",
        verbose=0,
    )
    debut = time.time()
    agent.learn(total_timesteps=pas)
    agent.save(sortie)
    part = np.mean(agent.part_gardee) if agent.part_gardee else float("nan")
    print(f"agent CVaR entraine en {time.time() - debut:.0f}s "
          f"({part * 100:.0f} % du lot retenu par mise a jour) -> {sortie.name}")
    return agent


def queue(valeurs: np.ndarray, alpha: float) -> float:
    """La moyenne des `alpha` pour cent de valeurs les plus mauvaises."""
    v = np.sort(np.asarray(valeurs))[::-1]  # decroissant : le pire d'abord
    k = max(1, int(np.ceil(alpha * v.size)))
    return float(v[:k].mean())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=365)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--pas", type=int, default=600_000)
    p.add_argument("--entrainer", action="store_true")
    p.add_argument("--graines", type=int, default=2)
    args = p.parse_args()

    from .baselines import prevoyant
    from .resultats import mesurer
    from .train import politique_agent

    DOSSIER.mkdir(parents=True, exist_ok=True)
    if args.entrainer:
        for g in range(args.graines):
            entrainer(args.pas, seed=g, sortie=DOSSIER / f"cvar_{g}")

    # on mesure la queue, pas seulement la moyenne : il faut rejouer les
    # journees une par une pour avoir leur distribution
    def par_journee(politique) -> tuple[np.ndarray, dict]:
        env = WiigaEnv(seed=0)
        heures = []
        for j in range(args.journees):
            env.jour_fixe = j % 365
            obs, _ = env.reset(seed=args.seed + j)
            fini = False
            while not fini:
                obs, _, ar, tr, info = env.step(politique(obs, env))
                fini = ar or tr
            heures.append(info["heures_a_sec"])
        return np.array(heures, dtype=float), {}

    lignes = {}
    candidats = {"regle ecrite": prevoyant}
    for g in range(args.graines):
        c = DOSSIER / f"graine_{g}.zip"
        if c.exists():
            candidats[f"PPO moyenne, graine {g}"] = politique_agent(PPO.load(c))
    # Cherche par motif plutot que par index. La version precedente n'ouvrait que
    # `cvar_0.zip` et `cvar_1.zip` ; l'agent entraine sur le disque s'appelait
    # `cvar_essai.zip`, donc la commande tournait, ne trouvait rien, et imprimait
    # un tableau sans aucune ligne CVaR - sans le dire. Le module entier est
    # ainsi reste absent de la soumission pendant qu'il avait l'air de marcher.
    cvars = sorted(DOSSIER.glob("cvar*.zip"))
    for c in cvars:
        candidats[f"PPO CVaR {int(ALPHA * 100)} %, {c.stem}"] = politique_agent(
            PPO.load(c)
        )
    if not cvars:
        print(f"\n(aucun agent cvar*.zip dans {DOSSIER} : le tableau ci-dessous "
              f"n'aura aucune ligne CVaR, et c'est dit plutot que subi)")

    print(f"\n{args.journees} journees, memes graines pour tout le monde\n")
    print(f"{'politique':<30}{'moyenne':>10}{'CVaR 20 %':>12}{'pire jour':>11}"
          f"{'jours > 2 h':>13}")
    print("-" * 76)
    for nom, pol in candidats.items():
        h, _ = par_journee(pol)
        d = {
            "moyenne": float(h.mean()),
            "cvar_20": queue(h, 0.20),
            "cvar_5": queue(h, 0.05),
            "pire_jour": float(h.max()),
            "jours_au_dessus_de_2h": int((h > 2).sum()),
        }
        lignes[nom] = d
        print(f"{nom:<30}{d['moyenne']:>10.3f}{d['cvar_20']:>12.3f}"
              f"{d['pire_jour']:>11.2f}{d['jours_au_dessus_de_2h']:>13}")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "alpha": ALPHA,
                "journees": args.journees,
                "seed": args.seed,
                "politiques": lignes,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\necrit dans {SORTIE}")


if __name__ == "__main__":
    main()
