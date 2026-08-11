"""La journée en une image.

L'argument de WIIGA ne se lit pas dans un tableau de moyennes. Il se voit sur
une journée : à 13 h l'agent pompe à pleine puissance vers un quartier qui ne
consomme rien, et à 19 h - réseau coupé, soleil couché, demande au maximum - la
cuve est pleine.

C'est ça, la batterie virtuelle. Le soleil de midi a été stocké sous forme
d'eau, pas de lithium.

    python -m wiiga.demo
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from .env import RESERVE_MINIMALE, SOURCES, WiigaEnv, solaire_horaire

SORTIE = Path(__file__).parent.parent / "journee.png"

COULEUR = {
    "solaire": "#e8a33d",
    "reseau": "#4a7fb5",
    "diesel": "#8c5a4a",
}
ENCRE = "#1d1f21"
PAPIER = "#faf7f2"


def jouer(agent, seed: int) -> tuple[WiigaEnv, list[dict]]:
    env = WiigaEnv(seed=seed)
    obs, _ = env.reset(seed=seed)
    fini = False
    while not fini:
        action, _ = agent.predict(obs, deterministic=True)
        obs, _, arret, tronque, _ = env.step(action)
        fini = arret or tronque
    return env, env.journal


def dessiner(env: WiigaEnv, journal: list[dict], sortie: Path = SORTIE) -> Path:
    heures = np.arange(24)
    coupures = env.reseau.coupures
    soleil = np.array([solaire_horaire(h) for h in heures])

    fig, (ax_ctx, ax_pompe, ax_cuve) = plt.subplots(
        3, 1, figsize=(13, 9.5), sharex=True,
        gridspec_kw={"height_ratios": [1.0, 1.1, 1.4], "hspace": 0.18},
    )
    fig.patch.set_facecolor(PAPIER)

    def bandes_coupure(ax):
        """Les heures sans réseau, sur les trois panneaux, pour lire d'un trait."""
        debut = None
        for h in range(25):
            coupe = coupures[h] if h < 24 else False
            if coupe and debut is None:
                debut = h
            elif not coupe and debut is not None:
                ax.axvspan(debut - 0.5, h - 0.5, color="#c94f4f", alpha=0.13, lw=0)
                debut = None

    # ---------------------------------------------------------------- contexte
    ax_ctx.set_facecolor(PAPIER)
    bandes_coupure(ax_ctx)
    ax_ctx.fill_between(heures, soleil, color=COULEUR["solaire"], alpha=0.35, lw=0)
    ax_ctx.plot(heures, soleil, color=COULEUR["solaire"], lw=2, label="soleil disponible")

    demande = env.zones[0].profil.volume_horaire()
    demande = demande / demande.max()
    ax_ctx.plot(heures, demande, color=ENCRE, lw=1.6, ls="--", label="demande (zone 1)")

    ax_ctx.set_ylim(0, 1.15)
    ax_ctx.set_ylabel("disponible / demandé")
    ax_ctx.legend(loc="upper left", frameon=False, fontsize=9)
    ax_ctx.set_title(
        "Une journée de saison chaude - le soleil, la demande, et les coupures",
        loc="left", fontsize=13, color=ENCRE, pad=10,
    )

    # ------------------------------------------------------------------ pompes
    ax_pompe.set_facecolor(PAPIER)
    bandes_coupure(ax_pompe)
    bas = np.zeros(24)
    for source in SOURCES:
        part = np.array([
            sum(p for p, s in zip(e["puissances"], e["sources"]) if s == source)
            for e in journal
        ])
        ax_pompe.bar(heures, part, bottom=bas, color=COULEUR[source], width=0.8,
                     label=source, lw=0)
        bas += part

    for e in journal:
        if e["passe_la_main"]:
            ax_pompe.plot(e["heure"], -0.12, marker="^", color=ENCRE, ms=7, clip_on=False)

    ax_pompe.set_ylabel("puissance pompée")
    ax_pompe.legend(loc="upper left", frameon=False, fontsize=9, ncol=3)
    ax_pompe.set_title(
        "Ce que l'agent fait, et avec quelle énergie  ·  ▲ = il a passé la main",
        loc="left", fontsize=11, color=ENCRE, pad=8,
    )

    # ------------------------------------------------------------------- cuves
    ax_cuve.set_facecolor(PAPIER)
    bandes_coupure(ax_cuve)
    niveaux = np.array([e["remplissages"] for e in journal])
    for i, zone in enumerate(env.zones):
        ax_cuve.plot(heures, niveaux[:, i], lw=2.4,
                     label=f"{zone.nom}", zorder=3)

    ax_cuve.axhline(RESERVE_MINIMALE, color=ENCRE, ls=":", lw=1.4)
    ax_cuve.text(0.15, RESERVE_MINIMALE + 0.02, "réserve de sécurité",
                 fontsize=8.5, color=ENCRE)
    ax_cuve.set_ylim(0, 1.05)
    ax_cuve.set_ylabel("remplissage des cuves")
    ax_cuve.set_xlabel("heure")
    ax_cuve.set_xticks(range(0, 24, 2))
    ax_cuve.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax_cuve.legend(loc="lower left", frameon=False, fontsize=9, ncol=3)

    for ax in (ax_ctx, ax_pompe, ax_cuve):
        for cote in ("top", "right"):
            ax.spines[cote].set_visible(False)
        ax.tick_params(colors=ENCRE, labelsize=9)

    fig.legend(handles=[Patch(facecolor="#c94f4f", alpha=0.2, label="réseau coupé")],
               loc="upper right", frameon=False, fontsize=9,
               bbox_to_anchor=(0.985, 0.975))

    fig.savefig(sortie, dpi=150, facecolor=PAPIER, bbox_inches="tight")
    plt.close(fig)
    return sortie


def raconter(env: WiigaEnv, journal: list[dict]) -> None:
    """Dire en français ce que la figure montre, heure par heure, aux moments clés."""
    solaire_midi = sum(
        p for e in journal if 11 <= e["heure"] <= 15
        for p, s in zip(e["puissances"], e["sources"]) if s == "solaire"
    )
    soir = [e for e in journal if 18 <= e["heure"] <= 21]
    niveaux_soir = [min(e["remplissages"]) for e in soir] or [0]
    coupures_soir = sum(1 for e in soir if not e["reseau"])

    print(f"  coupures dans la journée   : {env.reseau.heures_coupees} h")
    print(f"  pompé au soleil entre 11h et 15h : {solaire_midi:.1f} de puissance")
    print(f"  coupures entre 18h et 21h  : {coupures_soir} h")
    print(f"  cuve la plus basse le soir : {min(niveaux_soir):.0%} de remplissage")
    print(f"  gasoil restant en fin de journée : {env.carburant:.0f} kWh")


if __name__ == "__main__":
    from stable_baselines3 import PPO

    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--modele", default=str(Path(__file__).parent.parent / "wiiga_agent"))
    args = p.parse_args()

    agent = PPO.load(args.modele)
    env, journal = jouer(agent, args.seed)
    raconter(env, journal)
    print(f"\nfigure écrite dans {dessiner(env, journal)}")
