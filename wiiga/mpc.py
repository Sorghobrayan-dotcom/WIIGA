"""L'adversaire que la litterature aurait choisi : une commande predictive.

Le depot compare l'agent a trois politiques ecrites a la main, et il balaie
meme les constantes de la meilleure. Il reste une objection que rien n'adresse,
et c'est la plus serieuse qu'un jury technique puisse faire :

> Vos quatre adversaires sont ecrits par vous. Personne, dans la litterature sur
> le pompage, n'ecrirait un `if` : on pose une commande predictive a horizon
> glissant et on la resout. Battez **ca**.

Ce module est cette commande. Le sigle usuel est MPC, *model predictive
control*, et c'est la methode de reference pour piloter un stockage sous
contrainte depuis les annees quatre-vingt-dix.

**Comment elle marche.** A chaque heure, elle resout un programme lineaire sur
les six heures a venir : combien d'energie tirer de chaque source, vers chaque
cuve, a chaque heure. Elle applique la premiere heure du plan, avance d'une
heure, et recommence avec l'information fraiche. C'est le principe de l'horizon
glissant : planifier loin, n'engager que le pas suivant.

**Ce qu'elle sait, et c'est exactement ce que l'agent sait.** La forme
normalisee du profil de chaque quartier et le multiplicateur du jour, dont elle
reconstruit la demande attendue ; la prevision de coupure a quatre heures ; le
soleil de l'heure ; le gasoil restant ; les niveaux de cuve. Rien de plus. Elle
ne voit pas les coupures reelles, elle voit la meme prevision imparfaite.

**Elle optimise le meme objectif que l'agent**, et c'est ce qui rend la
comparaison honnete. Le manque du quartier le plus mal servi est minimise par
la variable epigraphe `u_max` : minimiser un maximum est exactement ce qu'un
programme lineaire sait faire, et c'est la traduction exacte de la recompense
max-min de `env.py`. Un MPC qui minimiserait la somme aurait un objectif plus
facile et la comparaison serait faussee en sa faveur.

**Trois choses qu'elle n'a pas, et il faut les dire.** Elle ne parle pas a la
ville - aucune formulation de commande optimale ne modelise un canal de
credibilite, c'est precisement le trou que ce projet remplit. Elle ne rend pas
la main. Et son modele du reseau est l'esperance de la prevision, pas sa loi :
une commande predictive stochastique complete arbitrerait sur des scenarios, ce
qui est un autre travail.

Dependance : `scipy`, et elle n'est requise que par ce fichier. Le reste du
depot tourne sans elle.

Execution : `python -m wiiga.mpc`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .demande import prevision as prevision_demande
from .env import (
    HORIZON_RESEAU,
    RENDEMENT_POMPE,
    SOURCES,
    WiigaEnv,
    solaire_horaire,
)

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "mpc.json"

#: L'horizon de planification, en heures. Six, comme l'horizon de demande que
#: l'agent recoit : le pic du residentiel est a 19 h et le soleil se couche vers
#: 17 h, donc en dessous de six l'arbitrage n'est pas visible. Au-dela, la
#: prevision de coupure n'existe plus et on planifierait sur du vide.
HORIZON = 6

#: Ce que coute une unite de manque dans l'objectif, en face du prix de
#: l'energie. Assez grand pour que servir la ville domine toujours l'economie
#: d'un kilowattheure : a 10 000, laisser un metre cube non servi coute plus
#: cher que n'importe quelle facon de le pomper.
PRIX_DU_MANQUE = 10_000.0


def _plan(env: WiigaEnv, heure: int) -> np.ndarray | None:
    """Resoudre l'horizon et rendre l'action de la premiere heure.

    Les variables, dans l'ordre ou `linprog` les recoit :

        e[z, t, s]   energie tiree pour la zone z, a l'heure t, de la source s
        m[z, t]      volume non servi a la zone z a l'heure t
        u            le pire manque cumule parmi les zones (variable epigraphe)

    Rend `None` si le solveur echoue, auquel cas l'appelant retombe sur une
    action nulle plutot que sur une action inventee.
    """
    from scipy.optimize import linprog

    nz, H = env.n_zones, HORIZON
    ns = len(SOURCES)
    n_e = nz * H * ns
    n_m = nz * H
    n_tot = n_e + n_m + 1

    def ie(z, t, s):
        return (z * H + t) * ns + s

    def im(z, t):
        return n_e + z * H + t

    iu = n_e + n_m

    # --- ce que le controleur croit de l'avenir ------------------------------
    # la prevision de coupure ne porte que quatre heures : au-dela on prolonge
    # par la derniere valeur connue plutot que d'inventer une loi
    prev = env.reseau.prevision(heure, HORIZON_RESEAU)
    dispo = [float(1.0 - prev[min(t, len(prev) - 1)]) for t in range(H)]

    soleil = [
        solaire_horaire((heure + t) % 24) * env.jour.ensoleillement for t in range(H)
    ]
    rendement = np.zeros((H, ns))
    for t in range(H):
        rendement[t, 0] = min(1.0, soleil[t] / 0.2) if soleil[t] > 0 else 0.0
        rendement[t, 1] = dispo[t]
        rendement[t, 2] = 1.0

    prix = np.zeros((H, ns))
    for t in range(H):
        h = (heure + t) % 24
        pointe = 18 <= h <= 22
        prix[t, 1] = env.prix["reseau_pointe"] if pointe else env.prix["reseau"]
        prix[t, 2] = env.prix["diesel"]

    # la demande attendue : la forme normalisee du profil, remise a l'echelle du
    # jour par le multiplicateur - les deux seules choses que l'agent observe
    besoin = np.zeros((nz, H))
    for z, zone in enumerate(env.zones):
        courbe = zone.profil.courbe()
        reference = zone.profil.volume_horaire()
        fenetre = prevision_demande(zone.profil, heure, H)
        echelle = float(reference.sum()) * env.jour.multiplicateur / courbe.sum()
        besoin[z] = np.asarray(fenetre, dtype=float) * echelle

    # --- objectif ------------------------------------------------------------
    c = np.zeros(n_tot)
    for z in range(nz):
        for t in range(H):
            for s in range(ns):
                c[ie(z, t, s)] = prix[t, s]
    c[iu] = PRIX_DU_MANQUE

    A_ub, b_ub = [], []

    # --- le pire quartier majore chaque quartier -----------------------------
    # u >= somme des manques de la zone z. Minimiser u, c'est minimiser le pire
    # des trois : la traduction lineaire exacte de la recompense max-min.
    for z in range(nz):
        ligne = np.zeros(n_tot)
        for t in range(H):
            ligne[im(z, t)] = 1.0
        ligne[iu] = -1.0
        A_ub.append(ligne)
        b_ub.append(0.0)

    # --- puissance de pompe --------------------------------------------------
    for z, zone in enumerate(env.zones):
        for t in range(H):
            ligne = np.zeros(n_tot)
            for s in range(ns):
                ligne[ie(z, t, s)] = 1.0
            A_ub.append(ligne)
            b_ub.append(float(zone.puissance_kw))

    # --- gasoil : la reserve du jour, pas davantage --------------------------
    ligne = np.zeros(n_tot)
    for z in range(nz):
        for t in range(H):
            ligne[ie(z, t, 2)] = 1.0
    A_ub.append(ligne)
    b_ub.append(float(env.carburant))

    # --- dynamique de cuve ---------------------------------------------------
    # V[z,t+1] = V[z,t] + entrees - (besoin - manque), avec 0 <= V <= capacite.
    # Ecrit en cumule : chaque contrainte porte sur les t premieres heures.
    for z, zone in enumerate(env.zones):
        for t in range(H):
            haut = np.zeros(n_tot)
            bas = np.zeros(n_tot)
            for k in range(t + 1):
                for s in range(ns):
                    gain = rendement[k, s] * RENDEMENT_POMPE
                    haut[ie(z, k, s)] = gain
                    bas[ie(z, k, s)] = -gain
                haut[im(z, k)] = 1.0
                bas[im(z, k)] = -1.0
            besoins = float(besoin[z, : t + 1].sum())
            # V <= capacite
            A_ub.append(haut)
            b_ub.append(zone.capacite - zone.volume + besoins)
            # V >= 0
            A_ub.append(bas)
            b_ub.append(zone.volume - besoins)

    # le manque ne peut pas depasser le besoin de l'heure
    bornes = [(0.0, None)] * n_tot
    for z in range(nz):
        for t in range(H):
            bornes[im(z, t)] = (0.0, float(besoin[z, t]))

    r = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub), bounds=bornes,
                method="highs")
    if not r.success:
        return None

    # --- n'engager que la premiere heure -------------------------------------
    action = np.zeros(env.action_space.shape[0], dtype=np.float32)
    for z, zone in enumerate(env.zones):
        tirages = [r.x[ie(z, 0, s)] for s in range(ns)]
        total = sum(tirages)
        s = int(np.argmax(tirages)) if total > 1e-9 else 0
        action[2 * z] = float(np.clip(total / zone.puissance_kw, 0.0, 1.0))
        action[2 * z + 1] = (s + 0.5) / 3.0
    action[-2] = 0.0  # ne rend jamais la main
    action[-1] = 0.0  # ne parle jamais a la ville
    return action


def politique_mpc(obs, env: WiigaEnv) -> np.ndarray:
    """La commande predictive, dans la meme signature que toutes les autres."""
    plan = _plan(env, env.heure)
    if plan is None:
        return np.zeros(env.action_space.shape[0], dtype=np.float32)
    return plan


def main() -> None:
    from .train import MODELE_PUBLIE

    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=365)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--modele", default=MODELE_PUBLIE)
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .baselines import POLITIQUES
    from .resultats import LITRES_SURVIE, mesurer
    from .train import politique_agent

    politiques = {
        "commande predictive (MPC)": politique_mpc,
        "prevoyant (regle ecrite)": POLITIQUES["prévoyant (règle écrite)"],
        "agent WIIGA (PPO)": politique_agent(PPO.load(args.modele)),
    }

    print(f"\n{args.journees} journees, memes graines pour tout le monde, "
          f"horizon {HORIZON} h\n")
    print(f"{'politique':<28}{'h a sec/j':>11}{'pire quartier':>15}"
          f"{'personnes/j':>13}{'FCFA/j':>10}{'L gasoil/j':>12}")
    print("-" * 89)

    lignes = {}
    for nom, pol in politiques.items():
        m = mesurer(pol, args.journees, args.seed)
        lignes[nom] = m
        print(f"{nom:<28}{m['heures_a_sec_par_jour']:>11.3f}"
              f"{m['heures_a_sec_pire_zone']:>15.3f}"
              f"{m['litres_manquants_par_jour'] / LITRES_SURVIE:>13.0f}"
              f"{m['fcfa_par_jour']:>10.0f}{m['litres_gasoil_par_jour']:>12.1f}")

    mpc = lignes["commande predictive (MPC)"]["heures_a_sec_par_jour"]
    agent = lignes["agent WIIGA (PPO)"]["heures_a_sec_par_jour"]
    ecart = (mpc - agent) / mpc * 100 if mpc > 0 else 0.0
    print()
    if agent <= mpc:
        print(f"l'agent bat la commande predictive de {ecart:.0f} %")
    else:
        print(f"la commande predictive bat l'agent de {-ecart:.0f} % "
              f"- a dire tel quel")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                "modele": args.modele,
                "horizon_heures": HORIZON,
                "mesures": lignes,
                "agent_bat_le_mpc": bool(agent <= mpc),
                "ecart_pct": ecart,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\necrit dans {SORTIE}")


if __name__ == "__main__":
    main()
