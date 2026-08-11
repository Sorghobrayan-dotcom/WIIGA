"""Le réseau électrique tel qu'il est, pas tel que la littérature le suppose.

Presque tous les travaux d'apprentissage par renforcement sur le pompage d'eau
supposent un réseau disponible : l'agent arbitre entre un tarif de pointe et un
tarif creux. C'est la question d'un pays où le courant est là.

Ici il ne l'est pas. Le délestage est la contrainte qui structure la journée, et
un agent qui l'ignore optimise un problème que personne n'a. Ce module en fait
une variable de premier rang, avec les trois propriétés qui le rendent difficile :

  il est probable plutôt que certain - l'agent reçoit une prévision, pas la
  vérité, et doit décider sous incertitude ;

  il persiste - une coupure qui commence dure des heures, donc l'erreur n'est pas
  ponctuelle, elle se paie longtemps ;

  il tombe au pire moment - la probabilité culmine sur la pointe du soir, quand
  la demande en eau culmine aussi et que le solaire est déjà couché.

La conséquence, et c'est tout l'intérêt : la bonne politique n'est pas d'acheter
au moins cher. C'est de **remplir avant**.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RegimeDelestage:
    """Le profil de coupures d'une saison.

    `risque_horaire` est la probabilité qu'une coupure DÉBUTE à cette heure-là,
    heure par heure sur 24. `persistance` est la probabilité qu'une coupure en
    cours continue à l'heure suivante, ce qui donne des pannes de plusieurs
    heures plutôt qu'un bruit qui clignote.
    """

    nom: str
    risque_horaire: np.ndarray
    persistance: float
    fiabilite_prevision: float
    """Entre 0 et 1. À 1 la prévision annonce la vérité, à 0 elle est du bruit.

    Jamais 1 : une prévision parfaite dispenserait l'agent de gérer le risque,
    et gérer le risque est précisément ce qu'on lui demande d'apprendre.
    """


def _profil(pointe: float, base: float) -> np.ndarray:
    """Un risque bas la nuit, qui monte vers la pointe du soir et retombe."""
    heures = np.arange(24)
    # centré sur 19h, la pointe d'éclairage domestique
    cloche = np.exp(-((heures - 19) ** 2) / 8.0)
    # une seconde bosse plus faible en milieu de journée, la climatisation
    cloche += 0.45 * np.exp(-((heures - 14) ** 2) / 10.0)
    return np.clip(base + (pointe - base) * cloche / cloche.max(), 0.0, 1.0)


#: Saison des pluies : le barrage produit, les coupures sont rares et courtes.
HIVERNAGE = RegimeDelestage(
    nom="hivernage",
    risque_horaire=_profil(pointe=0.10, base=0.01),
    persistance=0.45,
    fiabilite_prevision=0.80,
)

#: Saison sèche chaude : c'est le régime qui décide si le projet sert à quelque
#: chose. Mars-mai à Ouagadougou, quarante degrés, et le réseau lâche tous les
#: soirs. Un agent entraîné seulement sur l'hivernage est inutile ici.
SAISON_CHAUDE = RegimeDelestage(
    nom="saison chaude",
    risque_horaire=_profil(pointe=0.55, base=0.06),
    persistance=0.72,
    fiabilite_prevision=0.55,
)

#: Saison sèche tempérée : novembre-février. Le barrage a fini de se remplir mais
#: ne se recharge plus, et la demande n'a pas encore décollé. Le réseau tient la
#: plupart des soirs sans pour autant être celui de l'hivernage.
SAISON_TEMPEREE = RegimeDelestage(
    nom="saison tempérée",
    risque_horaire=_profil(pointe=0.28, base=0.03),
    persistance=0.60,
    fiabilite_prevision=0.68,
)

REGIMES = {r.nom: r for r in (HIVERNAGE, SAISON_TEMPEREE, SAISON_CHAUDE)}

#: Quel réseau va avec quelle saison. La correspondance est ici plutôt que dans
#: l'environnement parce que c'est une affirmation sur le pays, pas sur le code :
#: le délestage suit le niveau du barrage et la pointe des climatiseurs, donc il
#: suit la saison. Sans cette table, la saison pilotait la demande et le soleil
#: mais laissait le réseau identique toute l'année - un simulateur qui se
#: contredisait lui-même.
REGIME_PAR_SAISON = {
    "pluies": HIVERNAGE,
    "sèche tempérée": SAISON_TEMPEREE,
    "sèche chaude": SAISON_CHAUDE,
}


class Reseau:
    """Le réseau électrique sur une journée, tiré au sort puis observé.

    Deux méthodes, et la distance entre les deux est le sujet :
    `disponible()` dit ce qui EST, `prevision()` dit ce que l'exploitant CROIT.
    L'agent n'a droit qu'à la seconde.
    """

    def __init__(self, regime: RegimeDelestage, rng: np.random.Generator) -> None:
        self.regime = regime
        self.rng = rng
        self.coupures = np.zeros(24, dtype=bool)
        self._prevu = np.zeros(24, dtype=np.float32)

    def nouvelle_journee(self) -> None:
        """Tirer les coupures de la journée, puis la prévision qui en est faite."""
        coupures = np.zeros(24, dtype=bool)
        en_cours = False
        for h in range(24):
            if en_cours:
                en_cours = self.rng.random() < self.regime.persistance
            else:
                en_cours = self.rng.random() < self.regime.risque_horaire[h]
            coupures[h] = en_cours
        self.coupures = coupures

        # La prévision : la vérité mélangée au risque a priori, dans la
        # proportion que la fiabilité du régime autorise. En saison chaude elle
        # est à peine meilleure qu'une moyenne, ce qui est le cas réel.
        f = self.regime.fiabilite_prevision
        self._prevu = np.clip(
            f * coupures.astype(np.float32) + (1 - f) * self.regime.risque_horaire,
            0.0,
            1.0,
        ).astype(np.float32)

    def disponible(self, heure: int) -> bool:
        return not bool(self.coupures[heure % 24])

    def prevision(self, heure: int, horizon: int = 4) -> np.ndarray:
        """Le risque annoncé pour les `horizon` prochaines heures.

        C'est la seule information sur le réseau que l'agent reçoit, et c'est ce
        qui lui permet d'apprendre à remplir avant plutôt qu'à subir.
        """
        heures = (np.arange(heure, heure + horizon)) % 24
        return self._prevu[heures]

    @property
    def heures_coupees(self) -> int:
        return int(self.coupures.sum())
