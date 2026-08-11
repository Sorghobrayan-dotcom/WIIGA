"""Prévenir les gens, et payer en crédibilité.

L'agent dispose d'une action qui ne touche aucune pompe : **dire à la ville de
remplir ses bidons avant la coupure**. Par SMS, par radio de quartier, par le
crieur du marché - le canal importe peu, le mécanisme est le même.

Cette action n'existe nulle part dans la littérature sur le pompage, et pour une
raison qui n'a rien de technique : **en Europe personne ne stocke l'eau chez
soi**. Le « demand response » publié déplace de la charge industrielle par la
tarification. Ici chaque foyer a des bidons, et une phrase à 17 h déplace plus
d'eau qu'une heure de groupe électrogène.

Trois propriétés en font un vrai problème d'apprentissage plutôt qu'un bouton :

**Prévenir avance la demande, ça ne la supprime pas.** Les foyers remplissent
maintenant ce qu'ils auraient bu plus tard. La cuve est donc *plus* sollicitée
dans l'heure qui suit, et moins pendant la coupure. L'agent échange une tension
immédiate contre une tension future - et se trompe s'il alerte quand la cuve est
déjà basse.

**Le coût de l'action est l'efficacité future de cette même action.** Alerter à
tort ne coûte ni gasoil ni argent : ça coûte l'écoute. Une ville qu'on a
dérangée pour rien trois fois ne remplit plus ses bidons la quatrième.

**La crédibilité se perd bien plus vite qu'elle ne se gagne.** C'est vrai des
gens, et c'est ce qui rend la parcimonie obligatoire plutôt que souhaitable.

Conséquence pour l'apprentissage : l'agent ne peut pas se contenter de piloter.
Il doit **prévoir la coupure pour n'alerter que lorsqu'il a raison**, avec une
prévision qui n'est jamais fiable à cent pour cent. La calibration devient une
compétence apprise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Part des foyers qui remplissent leurs bidons quand la confiance est totale.
#:
#: Tout le monde ne réagit jamais : il y a ceux qui n'ont pas reçu le message,
#: ceux qui n'ont pas de récipient libre, ceux qui sont au travail. 45 % est déjà
#: généreux et l'ordre de grandeur est ce qui compte : c'est plus que ce qu'un
#: groupe électrogène peut compenser, ce qui est tout l'argument.
REPONSE_MAX = 0.45

#: Combien la confiance monte après une alerte suivie d'une vraie coupure.
MONTEE = 0.04

#: Combien elle tombe après une fausse alerte.
#:
#: Presque quatre fois la montée, et l'asymétrie n'est pas un réglage : elle est
#: la propriété qu'on veut modéliser. Une réputation se construit sur des mois et
#: se perd en une soirée. Sans elle, l'agent apprendrait à alerter tous les jours.
CHUTE = 0.15

#: Confiance au premier jour. La régie n'est ni crue ni méprisée.
CONFIANCE_INITIALE = 0.55

#: Le fond de la défiance. **Négatif, et c'est le correctif le plus important du
#: mécanisme.**
#:
#: Une première version arrêtait la confiance à zéro. Mesuré : une fois au
#: plancher, mentir devenait *gratuit* - la soustraction était écrêtée, donc plus
#: aucune fausse alerte ne coûtait quoi que ce soit, tandis que la réponse des
#: foyers valait déjà zéro. L'état était absorbant et sans coût, et l'agent y
#: tombait puis y restait en émettant sept alertes par jour à 57 % de justesse :
#: du bruit que rien ne pénalisait plus.
#:
#: En dessous de zéro il n'y a pas « pas de confiance », il y a de la défiance
#: active. Une régie qui a crié au loup cinquante fois n'est pas à égalité avec
#: une régie inconnue : elle doit d'abord remonter le trou qu'elle a creusé. La
#: réponse des foyers reste nulle sur toute la zone négative - on ne peut pas
#: répondre moins que pas du tout - mais chaque mensonge continue de coûter.
DEFIANCE_MAX = -1.0

#: Dans combien d'heures une alerte doit être suivie d'une coupure pour être
#: jugée juste. Au-delà, prévenir n'a servi à rien : les bidons sont déjà bus.
FENETRE_JUGEMENT = 4

#: Combien d'heures devant on puise pour remplir les bidons. Les foyers avancent
#: la consommation des prochaines heures, pas celle de la semaine.
PORTEE_DEPLACEMENT = 6

#: En combien d'heures les bidons remplis à l'annonce redeviennent vides.
#:
#: Une annonce lancée pendant que la ville a déjà fait ses réserves déplace
#: d'autant moins d'eau qu'il reste peu de place dans les récipients. C'est un
#: rendement décroissant, **pas** un garde-fou : mesuré, le remplissage ne
#: dépasse jamais la moitié à confiance initiale, parce que les foyers boivent
#: aussi vite qu'ils stockent. Ce qui décourage réellement le bavardage est
#: social et vit dans `alerter()`.
VIDAGE_BIDONS = PORTEE_DEPLACEMENT


@dataclass
class Crediteur:
    """Ce que la ville pense de la régie, et comment ça évolue.

    Un scalaire suffit : ce qu'on modélise est l'écoute moyenne d'une ville, pas
    l'opinion de chaque foyer. Le raffiner par quartier serait facile et
    n'apporterait rien tant que l'alerte est diffusée partout à la fois.
    """

    confiance: float = CONFIANCE_INITIALE
    alertes: int = 0
    justes: int = 0
    #: Alertes lancées et pas encore jugées : (heure, est-ce une répétition).
    en_attente: list[tuple[int, bool]] = field(default_factory=list)

    @property
    def reponse(self) -> float:
        """Part des foyers qui remplissent effectivement leurs bidons.

        Écrêtée à zéro : sous la défiance, personne ne bouge, et on ne peut pas
        répondre moins que pas du tout. La confiance, elle, continue de descendre
        - c'est ce qui distingue la profondeur du trou de son existence.
        """
        return REPONSE_MAX * max(0.0, self.confiance)

    @property
    def justesse(self) -> float:
        return self.justes / self.alertes if self.alertes else 0.0

    def alerter(self, heure: int) -> float:
        """Lancer l'alerte, et retourner la part de foyers qui va répondre.

        **Se répéter, c'est parler alors qu'on attend encore d'être jugé.** Une
        annonce lancée pendant qu'une précédente n'a pas encore été confirmée ou
        démentie ne rapporte aucune crédibilité, même si la coupure vient : la
        ville n'a rien appris de plus. Elle coûte en revanche le même prix si la
        coupure ne vient pas.

        Deux définitions plus faibles ont été essayées et écartées par la mesure.
        Comparer à l'heure de l'alerte précédente laissait fuir l'état d'un jour
        sur l'autre - une alerte à 2 h du matin passait pour la répétition de
        celle de 15 h la veille. Se fier au remplissage des bidons ne mordait
        pas : à confiance initiale les récipients ne dépassent jamais la moitié,
        et quatre annonces collées *gagnaient* de la confiance au lieu d'en
        perdre. La file d'attente de jugement, elle, ne dépend d'aucun réglage.
        """
        self.alertes += 1
        self.en_attente.append((heure, bool(self.en_attente)))
        return self.reponse

    def verifier(self, heure: int, coupures: list[bool]) -> None:
        """Juger les alertes dont la fenêtre vient de se refermer.

        `coupures[h]` dit si le réseau était effectivement coupé à l'heure h.
        Une alerte est juste si une coupure est survenue dans les quatre heures
        qui ont suivi. Sinon la ville a été dérangée pour rien.

        **Une répétition ne rapporte rien et coûte autant.** Redire la même chose
        une heure plus tard n'est pas une seconde prédiction réussie : personne
        ne remercie deux fois pour le même avertissement. Mais si la coupure ne
        vient pas, la ville a bien été dérangée deux fois, et elle compte les
        deux. L'asymétrie rend le bavardage strictement perdant en espérance,
        sans qu'on ait eu à inventer une pénalité pour l'interdire.
        """
        encore = []
        for depart, repete in self.en_attente:
            if heure - depart < FENETRE_JUGEMENT:
                encore.append((depart, repete))
                continue
            fenetre = coupures[depart + 1 : depart + 1 + FENETRE_JUGEMENT]
            if any(fenetre):
                self.justes += 1
                if not repete:
                    self.confiance = min(1.0, self.confiance + MONTEE)
            else:
                self.confiance = max(DEFIANCE_MAX, self.confiance - CHUTE)
        self.en_attente = encore

    def solder(self, coupures: list[bool]) -> None:
        """Juger ce qui reste en fin de journée, pour ne rien laisser impuni."""
        self.verifier(10_000, coupures)


def deplacer_demande(horaire: np.ndarray, heure: int, part: float) -> np.ndarray:
    """Avancer une part de la demande des prochaines heures vers maintenant.

    Le volume total de la journée ne change pas : les bidons remplis à 17 h sont
    bus à 20 h. C'est un déplacement, et c'est pour cela que l'alerte n'est pas
    une baguette magique - elle tend la cuve tout de suite.
    """
    h = np.asarray(horaire, dtype=np.float64).copy()
    debut = heure + 1
    fin = min(len(h), debut + PORTEE_DEPLACEMENT)
    if debut >= len(h) or part <= 0.0:
        return h

    deplace = h[debut:fin].sum() * part
    h[debut:fin] *= 1.0 - part
    # tout arrive dans l'heure qui suit l'annonce : on va au robinet maintenant
    h[debut] += deplace
    return h
