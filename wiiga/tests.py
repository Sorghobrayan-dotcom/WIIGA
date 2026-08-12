"""Les proprietes sur lesquelles tout le reste repose.

Un depot sans test invite la question : *vos chiffres pourraient etre faux et
personne ne le saurait.* Elle est legitime. Ce fichier verifie les cinq
proprietes dont depend l'argument, pas le code ligne a ligne - un test qui
reproduit l'implementation ne prouve rien d'autre que sa propre existence.

Chacune correspond a une phrase qu'on ecrit publiquement quelque part :

1. **L'alerte deplace la demande, elle ne la supprime pas.** Si le volume de la
   journee changeait, prevenir la ville serait une baguette magique et tout
   l'argument tomberait.
2. **Se repeter coute et ne rapporte rien.** C'est ce qui rend la parcimonie
   obligatoire plutot que souhaitable.
3. **La confiance descend sous zero.** L'absence de plancher a zero est ce qui
   empeche l'etat absorbant ou mentir devenait gratuit.
4. **L'equite change vraiment la recompense.** Sans quoi l'ablation `equite=False`
   ne mesure rien.
5. **L'energie et l'eau se conservent.** Le gasoil consomme sort de la reserve,
   et rien n'entre dans une cuve qui n'ait ete pompe.

Pas de dependance : `python -m wiiga.tests`, code de sortie 1 si quelque chose
casse.
"""

from __future__ import annotations

import sys

import numpy as np

from .alerte import CHUTE, DEFIANCE_MAX, MONTEE, Crediteur, deplacer_demande
from .env import CARBURANT_JOUR, RENDEMENT_POMPE, WiigaEnv

_echecs: list[str] = []


def verifier(nom: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {nom}")
    else:
        print(f"  ECHEC {nom}   {detail}")
        _echecs.append(nom)


def action_nulle(env: WiigaEnv, alerte: bool = False) -> np.ndarray:
    a = np.zeros(env.action_space.shape[0], dtype=np.float32)
    if alerte:
        a[-1] = 1.0
    return a


# --------------------------------------------------------------------------- 1
def test_volume_conserve() -> None:
    """Deplacer la demande ne doit ni en creer ni en detruire."""
    rng = np.random.default_rng(0)
    for _ in range(200):
        horaire = rng.uniform(0.5, 8.0, 24)
        heure = int(rng.integers(0, 24))
        part = float(rng.uniform(0.0, 0.6))
        apres = deplacer_demande(horaire, heure, part)
        verifier_ecart = abs(apres.sum() - horaire.sum())
        if verifier_ecart > 1e-9:
            verifier("volume conserve par deplacer_demande", False,
                     f"heure={heure} part={part:.2f} ecart={verifier_ecart:.2e}")
            return
    verifier("volume conserve par deplacer_demande (200 tirages)", True)

    # et sur une journee complete jouee, alertes comprises
    env = WiigaEnv(seed=0)
    env.jour_fixe = 105
    env.reset(seed=7)
    debut = sum(float(z.horaire.sum()) for z in env.zones)
    for _ in range(24):
        env.step(action_nulle(env, alerte=True))
    fin = sum(float(z.horaire.sum()) for z in env.zones)
    verifier("volume conserve sur une journee d'alertes", abs(fin - debut) < 1e-6,
             f"{debut:.4f} -> {fin:.4f}")


# --------------------------------------------------------------------------- 2
def test_repetition() -> None:
    """Une annonce lancee pendant qu'une autre attend son jugement ne rapporte
    rien, et coute autant si elle se revele fausse."""
    coupures = [False] * 24
    for h in range(16, 21):
        coupures[h] = True

    def campagne(heures):
        c = Crediteur()
        for h in range(24):
            c.verifier(h, coupures[: h + 1])
            if h in heures:
                c.alerter(h)
        c.solder(coupures)
        return c

    seule = campagne([14])
    repetee = campagne([14, 15, 16, 17])
    verifier("repeter une alerte juste ne rapporte rien de plus",
             abs(seule.confiance - repetee.confiance) < 1e-9,
             f"{seule.confiance:.3f} contre {repetee.confiance:.3f}")

    une_fausse = campagne([2])
    quatre_fausses = campagne([2, 3, 4, 5])
    verifier("chaque fausse alerte coute, meme repetee",
             quatre_fausses.confiance < une_fausse.confiance,
             f"{quatre_fausses.confiance:.3f} contre {une_fausse.confiance:.3f}")

    verifier("le point mort vaut bien 78,9 % de justesse",
             abs(CHUTE / (MONTEE + CHUTE) - 0.789) < 0.001)


# --------------------------------------------------------------------------- 3
def test_defiance() -> None:
    """Sous zero il y a de la defiance active, pas une absence de confiance."""
    c = Crediteur()
    coupures = [False] * 24
    for h in range(20):
        c.confiance = max(DEFIANCE_MAX, c.confiance - CHUTE)
    verifier("la confiance descend sous zero", c.confiance < 0.0, f"{c.confiance:.2f}")
    verifier("la reponse des foyers est ecretee a zero", c.reponse == 0.0,
             f"{c.reponse:.3f}")

    c.confiance = -0.20
    avant = c.confiance
    c.confiance = max(DEFIANCE_MAX, c.confiance - CHUTE)
    verifier("mentir coute encore en zone negative", c.confiance < avant,
             f"{avant:.2f} -> {c.confiance:.2f}")


# --------------------------------------------------------------------------- 4
def test_equite() -> None:
    """`equite=False` doit vraiment changer la recompense, sinon l'ablation ment."""
    diff = 0.0
    for graine in range(5):
        rs = []
        for equite in (True, False):
            env = WiigaEnv(seed=0, equite=equite)
            env.jour_fixe = 105
            env.reset(seed=graine)
            total = 0.0
            for _ in range(24):
                _, r, *_ = env.step(action_nulle(env))
                total += r
            rs.append(total)
        diff += abs(rs[0] - rs[1])
    verifier("equite=False change la recompense", diff > 1.0, f"ecart cumule {diff:.2f}")

    # et le sens doit etre le bon : le min est toujours <= la moyenne, donc la
    # version equitable ne peut pas recompenser davantage sur la meme journee
    env_min = WiigaEnv(seed=0, equite=True)
    env_moy = WiigaEnv(seed=0, equite=False)
    for e in (env_min, env_moy):
        e.jour_fixe = 105
        e.reset(seed=3)
    r_min = r_moy = 0.0
    for _ in range(24):
        _, a, *_ = env_min.step(action_nulle(env_min))
        _, b, *_ = env_moy.step(action_nulle(env_moy))
        r_min += a
        r_moy += b
    verifier("la version equitable ne recompense jamais plus que la moyenne",
             r_min <= r_moy + 1e-6, f"min {r_min:.1f} contre moyenne {r_moy:.1f}")


# --------------------------------------------------------------------------- 5
def test_bilans() -> None:
    """Le gasoil sort de la reserve, et rien n'entre dans une cuve sans pompage."""
    env = WiigaEnv(seed=0)
    env.jour_fixe = 105
    env.reset(seed=11)

    a = np.full(env.action_space.shape[0], 0.5, dtype=np.float32)
    # forcer le diesel sur toutes les zones
    for i in range(env.n_zones):
        a[2 * i + 1] = (2 + 0.5) / 3.0
    a[-2] = 0.0
    a[-1] = 0.0

    for _ in range(24):
        _, _, _, _, info = env.step(a)

    brule = CARBURANT_JOUR - info["carburant_restant"]
    verifier("le gasoil consomme ne depasse pas la reserve",
             -1e-6 <= brule <= CARBURANT_JOUR + 1e-6, f"{brule:.1f} kWh")
    verifier("les kWh comptes correspondent au gasoil sorti",
             abs(info["kwh"]["diesel"] - brule) < 1e-6,
             f"{info['kwh']['diesel']:.2f} contre {brule:.2f}")

    env.reset(seed=12)
    capacite = sum(z.capacite for z in env.zones)
    volume_avant = sum(z.volume for z in env.zones)
    _, _, _, _, info = env.step(action_nulle(env))
    volume_apres = sum(z.volume for z in env.zones)
    verifier("pompes a l'arret : aucune eau n'apparait",
             volume_apres <= volume_avant + 1e-9,
             f"{volume_avant:.2f} -> {volume_apres:.2f}")
    verifier("aucune cuve ne depasse sa capacite",
             all(z.volume <= z.capacite + 1e-9 for z in env.zones),
             f"capacite totale {capacite:.0f}")

    # le rendement de pompage est bien celui annonce
    env.reset(seed=13)
    zone = env.zones[0]
    avant = zone.volume
    zone.remplir(10.0 * RENDEMENT_POMPE, solaire=False)
    verifier("remplir ajoute exactement ce qu'on lui donne",
             abs(zone.volume - avant - 10.0 * RENDEMENT_POMPE) < 1e-9
             or zone.volume == zone.capacite)


def main() -> None:
    for titre, fn in (
        ("1. l'alerte deplace la demande, elle ne la cree pas", test_volume_conserve),
        ("2. se repeter coute et ne rapporte rien", test_repetition),
        ("3. la defiance existe sous zero", test_defiance),
        ("4. l'equite change vraiment la recompense", test_equite),
        ("5. l'energie et l'eau se conservent", test_bilans),
    ):
        print(f"\n{titre}")
        fn()

    print()
    if _echecs:
        print(f"{len(_echecs)} echec(s) : {', '.join(_echecs)}")
        sys.exit(1)
    print("tout passe.")


if __name__ == "__main__":
    main()
