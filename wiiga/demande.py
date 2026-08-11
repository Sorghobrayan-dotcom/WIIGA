"""Ce que chaque quartier boit, et à quelle heure.

Un seul profil de demande pour toute la ville est une simplification qui tue le
projet, parce qu'elle supprime la question. Si tous les quartiers ont soif en
même temps, il n'y a rien à arbitrer : on pompe partout au même moment et on
subit. C'est quand les pics sont **décalés** que la batterie virtuelle a un sens
— on remplit celui de 19 h pendant que le soleil est encore là, avec l'énergie
que celui de 6 h n'utilise plus.

Trois profils, tirés de ce qu'est réellement une ville sahélienne :

  le marché ouvre tôt et vit le matin ;
  le quartier résidentiel se lave le soir, après le travail et la chaleur ;
  la zone mixte, avec école et dispensaire, creuse à midi.

Et une conséquence qui est le cœur du problème : le pic du résidentiel tombe à
19 h, c'est-à-dire **après le coucher du soleil et pendant la pointe de
délestage**. C'est le pire moment possible, et c'est le moment où l'eau est le
plus demandée. Tout le projet tient dans cet écart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ProfilZone:
    """Le rythme d'un quartier sur vingt-quatre heures."""

    nom: str
    habitants: int
    #: Heures des pics, et largeur de chaque pic.
    pics: tuple[tuple[float, float, float], ...]
    """(heure, hauteur, largeur) pour chaque pic de la journée."""
    base: float = 0.15
    #: Litres par habitant et par jour visés. L'OMS place le besoin de base à 50.
    litres_par_habitant: float = 50.0

    def courbe(self) -> np.ndarray:
        """La demande horaire normalisée, vingt-quatre valeurs."""
        heures = np.arange(24, dtype=np.float64)
        c = np.full(24, self.base)
        for centre, hauteur, largeur in self.pics:
            c += hauteur * np.exp(-((heures - centre) ** 2) / (2 * largeur**2))
        return c / c.max()

    def volume_horaire(self) -> np.ndarray:
        """La demande en m³ par heure, une fois la courbe mise à l'échelle."""
        besoin_jour = self.habitants * self.litres_par_habitant / 1000.0
        courbe = self.courbe()
        return courbe / courbe.sum() * besoin_jour


#: Le marché. Debout avant le jour, mort l'après-midi.
MARCHE = ProfilZone(
    nom="marché",
    habitants=6_000,
    pics=((6.0, 1.0, 1.6), (11.0, 0.45, 2.0)),
)

#: Le résidentiel dense. Son pic est à 19 h, sans soleil et en pleine pointe de
#: délestage : c'est le quartier qui rend le problème difficile.
RESIDENTIEL = ProfilZone(
    nom="résidentiel",
    habitants=12_000,
    pics=((7.0, 0.6, 1.4), (19.0, 1.0, 1.8)),
)

#: École et dispensaire. Un plateau de jour, rien la nuit.
MIXTE = ProfilZone(
    nom="mixte",
    habitants=4_000,
    pics=((8.0, 0.7, 2.2), (13.0, 0.8, 2.5)),
)

PROFILS = (MARCHE, RESIDENTIEL, MIXTE)


def prevision(profil: ProfilZone, heure: int, horizon: int) -> np.ndarray:
    """La demande annoncée pour les `horizon` prochaines heures, normalisée.

    C'est l'information sans laquelle la batterie virtuelle est impossible : pour
    décider de pomper à 13 h vers un quartier qui ne consomme rien à 13 h, il
    faut voir son pic de 19 h. Un agent qui n'observe que l'heure courante ne
    peut pas anticiper, quel que soit son entraînement.
    """
    courbe = profil.courbe()
    heures = (np.arange(heure, heure + horizon)) % 24
    return courbe[heures].astype(np.float32)
