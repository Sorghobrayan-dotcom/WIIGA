"""Précalculer tout ce que la console rejoue, et rien de plus.

La page de démonstration est un fichier statique : pas de serveur, pas de
fonction *serverless*, pas de requête réseau. Il faut donc que tout ce qu'un
visiteur peut demander existe déjà dedans.

Ce fichier joue chaque combinaison **ville × journée × politique** avec le modèle
entraîné et écrit les journaux heure par heure. Le navigateur ne fait ensuite que
les rejouer : il n'y a aucune intelligence dans la page, et c'est dit là-bas.

Les journées ne sont pas prises au hasard. Pour chaque ville on retient **une
journée par régime** — la saison des pluies, la saison sèche chaude, la saison
sèche tempérée — parce que c'est justement le fait que ces trois régimes
demandent des politiques opposées qui rend l'apprentissage nécessaire. Un
visiteur qui bascule de l'une à l'autre voit l'agent changer d'avis.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from wiiga.baselines import POLITIQUES  # noqa: E402
from wiiga.calendrier import OUAGADOUGOU, journee  # noqa: E402
from wiiga.env import WiigaEnv  # noqa: E402
from wiiga.tarifs import tarif_de  # noqa: E402
from wiiga.ville import CACHE, climat_de  # noqa: E402

GRAINE = 24

#: Les villes de la console, dans l'ordre d'affichage. Ouagadougou d'abord :
#: c'est la seule que l'agent ait vue à l'entraînement.
VILLES = ("Ouagadougou", "Chennai", "Nairobi", "Sydney", "Lima")


def journee_type(climat, saison: str) -> int | None:
    """Le jour du milieu d'un régime, pour éviter les bords.

    On prend la médiane des jours de cette saison plutôt que le premier venu :
    un jour de transition raconterait mal le régime qu'il est censé illustrer.
    """
    jours = [j for j in range(365) if journee(j, climat).saison == saison]
    return jours[len(jours) // 2] if jours else None


def jouer(politique, climat, tarif, jour: int) -> dict:
    env = WiigaEnv(seed=0, climat=climat, tarif=tarif)
    env.jour_fixe = jour
    obs, _ = env.reset(seed=GRAINE)
    capacites = [round(z.capacite, 1) for z in env.zones]
    fini = False
    while not fini:
        obs, _, arret, tronque, info = env.step(politique(obs, env))
        fini = arret or tronque

    # on ne garde que ce que la page dessine : un journal complet pèse trois fois
    # plus lourd pour rien
    heures = [
        {
            "reseau": bool(r["reseau"]),
            "soleil": round(float(r["soleil"]), 3),
            "remplissages": [round(float(x), 3) for x in r["remplissages"]],
            "sources": r["sources"],
            "puissances": [round(float(x), 2) for x in r["puissances"]],
            "besoins": [round(float(x), 2) for x in r["besoins"]],
            "alerte": bool(r["alerte"]),
            "confiance": round(float(r["confiance"]), 3),
            "cout": round(float(r["cout"])),
            "passe_la_main": bool(r["passe_la_main"]),
        }
        for r in env.journal
    ]
    return {
        "heures": heures,
        "capacites": capacites,
        "heures_a_sec": info["heures_a_sec"],
        "cout_total": round(float(info["cout_total"])),
        "kwh": {k: round(v, 1) for k, v in info["kwh"].items()},
        "litres_manquants": round(float(info["litres_manquants"])),
        "creux": round(float(info["creux_journee"]), 3),
    }


def construire() -> dict:
    from stable_baselines3 import PPO

    # la graine médiane des trois, pas la meilleure. Choisir la meilleure pour
    # les illustrations et publier la moyenne pour les chiffres serait une façon
    # discrète de mentir : `graines.json` donne les trois, et c'est celle du
    # milieu qu'on rejoue ici.
    modele = PPO.load(RACINE / "agents" / "graine_0")

    def agent(obs, env):
        a, _ = modele.predict(obs, deterministic=True)
        return a

    politiques = {"agent": agent, "regle": POLITIQUES["prévoyant (règle écrite)"]}
    disponibles = {p.stem for p in CACHE.glob("*.json")}

    villes = {}
    for nom in VILLES:
        climat = (
            OUAGADOUGOU
            if nom == "Ouagadougou"
            else climat_de(nom, hors_ligne=nom.lower() in disponibles)
        )
        tarif, connu = tarif_de(nom)

        jours = {}
        for saison in ("sèche chaude", "pluies", "sèche tempérée"):
            j = journee_type(climat, saison)
            if j is None:
                continue
            d = journee(j, climat)
            jours[saison] = {
                "numero": j,
                "temperature": round(d.temperature, 1),
                "evenement": d.evenement,
                "multiplicateur": round(d.multiplicateur, 2),
                "politiques": {
                    k: jouer(p, climat, tarif, j) for k, p in politiques.items()
                },
            }

        villes[nom] = {
            "latitude": round(climat.latitude, 2),
            "tmax": [round(v, 1) for v in climat.tmax],
            "soleil": [round(v, 1) for v in climat.soleil],
            "pluie": [round(v, 2) for v in climat.pluie],
            "devise": tarif.symbole,
            "par_usd": tarif.par_usd,
            "tarif_connu": connu,
            "jours": jours,
        }
        print(f"  {nom:<14}{len(jours)} régimes")

    env = WiigaEnv(seed=0)
    env.reset(seed=0)
    return {
        "villes": villes,
        "zones": [z.nom for z in env.zones],
        "habitants": [z.profil.habitants for z in env.zones],
        "graine": GRAINE,
    }


if __name__ == "__main__":
    d = construire()
    sortie = Path(__file__).resolve().parent / "scenarios.json"
    sortie.write_text(
        json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"\n{sortie.name} : {sortie.stat().st_size / 1024:.0f} Ko")
