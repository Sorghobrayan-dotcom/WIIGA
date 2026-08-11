"""Exporter une journee rejouable : l'agent et l'exploitant, meme graine.

Ne modifie rien dans WIIGA. Lit le journal que env.py tient deja.
"""
import json
import sys

from stable_baselines3 import PPO

sys.path.insert(0, r"C:\Users\techa\Desktop\WIIGA")

from wiiga.baselines import POLITIQUES, evaluer  # noqa: E402
from wiiga.env import WiigaEnv  # noqa: E402

MODELE = r"C:\Users\techa\Desktop\WIIGA\wiiga_agent.zip"
#: Choisie parce qu'elle colle aux moyennes sur 200 jours : l'exploitant y perd
#: 4 heures a sec contre 3,86 de moyenne, et 597 231 FCFA contre 687 581. Ce
#: n'est pas la journee la plus spectaculaire, c'est la plus representative.
GRAINE = 24


def jouer(politique, graine):
    env = WiigaEnv()
    obs, _ = env.reset(seed=graine)
    fini = False
    while not fini:
        obs, _, arret, tronque, info = env.step(politique(obs, env))
        fini = arret or tronque
    return env.journal, info


def main():
    modele = PPO.load(MODELE)

    def agent(obs, env):
        a, _ = modele.predict(obs, deterministic=True)
        return a

    politiques = {"agent": agent, "exploitant": POLITIQUES["exploitant (consigne fixe)"]}

    journees, bilans = {}, {}
    for nom, pol in politiques.items():
        journal, info = jouer(pol, GRAINE)
        journees[nom] = journal
        bilans[nom] = {k: (round(v, 3) if isinstance(v, float) else v)
                       for k, v in info.items()}

    # les moyennes sur 200 jours, pour le chiffre du dossier
    env = WiigaEnv()
    moyennes = {}
    for nom, pol in list(POLITIQUES.items()) + [("agent (PPO)", agent)]:
        moyennes[nom] = {k: round(v, 2) for k, v in
                         evaluer(pol, env, journees=200, seed=0).items()}

    sortie = {"graine": GRAINE, "journees": journees,
              "bilans": bilans, "moyennes": moyennes}
    chemin = (r"C:\Users\techa\AppData\Local\Temp\claude"
              r"\C--Users-techa-Desktop-lafia"
              r"\2a8a1b53-7517-4c0f-a9dc-fbac28a57579\scratchpad\journee.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)

    for nom, j in journees.items():
        sec = bilans[nom]["heures_a_sec"]
        print(f"{nom:12} {len(j)} heures, {sec} h a sec, "
              f"{bilans[nom]['cout_total']:.0f} FCFA")
    print("ecrit ->", chemin)


if __name__ == "__main__":
    main()
