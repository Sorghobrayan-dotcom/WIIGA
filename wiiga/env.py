"""L'environnement WIIGA : la cuve comme batterie.

L'idée qui tient tout le reste. Le solaire est gratuit à 13 h et absent à 19 h,
et c'est à 19 h que le quartier résidentiel a soif. Stocker cette énergie
demanderait des batteries au lithium — chères, polluantes, à remplacer dans huit
ans.

Sauf qu'il existe déjà un stockage sur place : **la cuve**. Pomper à 13 h avec du
soleil gratuit vers un quartier qui ne consomme rien à 13 h, ce n'est pas du
gaspillage, c'est du stockage. On ne stocke pas de l'électricité, on stocke du
travail déjà fait.

C'est aussi ce qui rend l'apprentissage nécessaire plutôt que décoratif. Pour
décider de remplir maintenant, l'agent doit tenir ensemble quatre choses qui
n'arrivent pas au même moment : le pic du quartier dans six heures, la course du
soleil, le risque de délestage du soir, et le gasoil qui reste. Une règle écrite
à la main n'arbitre pas quatre horizons.

Trois autres écarts avec la façon habituelle de poser ce problème :

**Le réseau tombe.** Voir `grid.py`. La littérature arbitre entre tarif de pointe
et tarif creux ; ici la question est de remplir avant que le courant parte.
L'agent reçoit une prévision de coupure, pas la coupure.

**L'agent a le droit de ne pas décider.** `passer la main` rend l'heure à la
consigne fixe de l'exploitant : ça coûte un peu et c'est sûr. Personne ne branche
une boîte noire sur l'eau d'une ville ; un agent qui sait dire « pas cette
heure-ci » est déployable.

**On optimise le quartier le plus mal servi, pas la facture.** La récompense lit
le minimum, pas la moyenne. Assécher un quartier pour en garder deux pleins est
excellent en moyenne, et inacceptable.

Le modèle hydraulique est un bilan de masse par cuve, pas une simulation EPANET.
C'est écrit ici plutôt que caché.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .alerte import VIDAGE_BIDONS, Crediteur, deplacer_demande
from .calendrier import OUAGADOUGOU, Climat, Journee, deformation_ramadan, journee
from .demande import PROFILS, ProfilZone, prevision
from .tarifs import OUAGADOUGOU as TARIF_OUAGA
from .tarifs import Tarif
from .grid import (
    REGIME_PAR_SAISON,
    REGIMES,
    SAISON_CHAUDE,
    RegimeDelestage,
    Reseau,
)

HEURES = 24
#: Combien d'heures devant l'agent voit la demande. Six, parce que le pic du
#: résidentiel est à 19 h et que le soleil se couche vers 17 h : en dessous de
#: six, l'arbitrage est invisible et la batterie virtuelle impossible.
HORIZON_DEMANDE = 6
#: Les instants regardés dans cet horizon, pour ne pas gonfler l'observation.
JALONS = (0, 2, 4, 6)
HORIZON_RESEAU = 4

#: Tarifs par défaut, en monnaie locale de la ville d'entraînement. Remplacés
#: par ceux du `Tarif` passé à l'environnement — voir `tarifs.py`, qui explique
#: pourquoi la monnaie est une couche de présentation et pas une unité de
#: mesure : ce projet compte d'abord en kWh, en litres et en personnes.
PRIX = TARIF_OUAGA.prix_locaux()
SOURCES = ("solaire", "reseau", "diesel")

#: kWh de groupe électrogène pour la journée, et c'est tout.
#:
#: Sans cette limite le problème n'existe pas : une première version laissait le
#: diesel illimité, et la mesure l'a montré tout de suite — une règle bête qui
#: bascule sur le groupe dès que le réseau tombe ne laissait jamais un quartier à
#: sec. Une régie a une cuve de gasoil, elle est petite, et la remplir dépend
#: d'un camion.
CARBURANT_JOUR = 320.0

#: Le remplissage sous lequel une régie n'accepte pas de descendre. Ce n'est pas
#: une contrainte hydraulique, c'est une marge : de quoi encaisser une coupure
#: plus longue que ce que la prévision annonçait.
RESERVE_MINIMALE = 0.35

#: m³ pompés par kWh. Ordre de grandeur d'une station de quartier.
RENDEMENT_POMPE = 0.55

#: Escompte de l'agent.
#:
#: 0,995 et non 0,98, et la différence est structurelle. Une journée fait vingt-
#: quatre pas ; à 0,98 l'horizon utile est d'une cinquantaine de pas, soit deux
#: jours. C'est assez pour piloter des cuves, qui repartent pleines chaque matin,
#: et bien trop court pour une réputation, qui met une dizaine de journées à se
#: construire ou à s'effondrer. À 0,995 l'horizon couvre environ huit jours :
#: l'agent peut enfin voir que se taire aujourd'hui vaut de l'eau la semaine
#: prochaine.
#:
#: Importé par `train.py` plutôt que réécrit là-bas : deux valeurs qui
#: divergeraient seraient invisibles et fausseraient le prix du crédit.
GAMMA = 0.995

#: Part des journées d'entraînement où la crédibilité est retirée au hasard.
#: Voir `reset` — c'est ce qui empêche l'agent de rester coincé au plancher.
PART_REDEMARRAGE = 0.10

#: Ce que vaut la crédibilité de la régie, en unités de récompense.
#:
#: Une fausse alerte coûte 0,15 de confiance, donc 6 points — l'ordre de grandeur
#: d'une demi-heure de fonctionnement. Une alerte juste et non répétée en rapporte
#: 1,6. Le rapport entre les deux n'est pas un réglage : il vient tout entier de
#: l'asymétrie `MONTEE`/`CHUTE`, et ce prix ne fait que la mettre à l'échelle du
#: reste de la récompense. Le seuil de décision reste 78,9 % quelle qu'en soit la
#: valeur ; seule la visibilité du gradient change.
PRIX_CONFIANCE = 40.0

#: La pompe d'une zone est dimensionnée sur SON pic, pas sur une constante.
#:
#: Une première version donnait 20 kW à tout le monde : la ville demandait
#: 1 100 m³/jour et les trois pompes à fond vingt-quatre heures n'en donnaient
#: que 792. Aucune politique ne pouvait servir la ville, donc aucune ne pouvait
#: être meilleure qu'une autre, et le banc d'essai ne mesurait plus rien.
#:
#: Ce facteur est ce qui rend l'arbitrage possible : à 2,5 fois le pic horaire,
#: une pompe peut remplir la cuve en avance pendant les heures creuses. En
#: dessous de 1, elle court après la demande et il n'y a plus de décision à
#: prendre.
MARGE_POMPE = 2.5


@dataclass
class Zone:
    """Un quartier : ses habitants, son rythme, sa cuve."""

    profil: ProfilZone
    capacite: float
    volume: float
    #: kW à pleine puissance, dimensionné sur le pic de cette zone.
    puissance_kw: float = 20.0
    #: La demande horaire **de cette journée-là**, en m³, calculée une fois au
    #: reset. Elle porte déjà la chaleur, la fête et, s'il y a lieu, le
    #: déplacement du Ramadan vers le soir.
    horaire: np.ndarray | None = None
    #: Combien, dans la cuve, a été pompé au soleil. Suivi en mélange, ce qui
    #: permet de dire à 19 h quelle part de l'eau bue vient du solaire de midi —
    #: le chiffre qui prouve que la batterie virtuelle fonctionne.
    volume_solaire: float = 0.0
    heures_a_sec: int = 0
    litres_manquants: float = 0.0

    @property
    def nom(self) -> str:
        return self.profil.nom

    @property
    def remplissage(self) -> float:
        return self.volume / self.capacite

    @property
    def part_solaire(self) -> float:
        return self.volume_solaire / self.volume if self.volume > 1e-6 else 0.0

    def remplir(self, volume: float, solaire: bool) -> None:
        place = max(0.0, self.capacite - self.volume)
        entre = min(volume, place)
        self.volume += entre
        if solaire:
            self.volume_solaire += entre

    def servir(self, demande: float) -> float:
        """Servir ce qu'on peut, et retourner la part solaire de ce qui est bu."""
        servi = min(demande, self.volume)
        part = self.part_solaire
        if self.volume > 1e-6:
            self.volume_solaire -= servi * part
        self.volume -= servi
        manque = demande - servi
        self.litres_manquants += manque * 1000.0
        if manque > 1e-6:
            self.heures_a_sec += 1
        return servi * part


def solaire_horaire(heure: int) -> float:
    """Zéro la nuit, une cloche entre 7 h et 17 h."""
    if 7 <= heure <= 17:
        return float(np.sin(np.pi * (heure - 7) / 10.0))
    return 0.0


def consigne_exploitant(heure: int, n: int) -> np.ndarray:
    """Ce qui tourne aujourd'hui, et le refuge quand l'agent passe la main.

    À fond la nuit sur le réseau, au ralenti le jour. Sûr et cher : le compromis
    qu'un exploitant prudent choisit quand il n'a pas d'outil pour faire mieux.
    """
    plein = 1.0 if (heure < 6 or heure >= 22) else 0.35
    return np.full(n, plein, dtype=np.float32)


class WiigaEnv(gym.Env):
    """Vingt-quatre heures de pompage sous délestage, la cuve servant de batterie."""

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        profils: tuple[ProfilZone, ...] = PROFILS,
        #: Laissé à None, le réseau suit la saison du jour tiré — c'est le mode
        #: normal. Forcer un régime sert à l'expérience inverse : montrer qu'un
        #: agent entraîné sur la seule saison chaude s'effondre en hivernage.
        regime: RegimeDelestage | str | None = None,
        cout_passer_la_main: float = 3.0,
        seed: int | None = None,
        climat: Climat = OUAGADOUGOU,
        #: Fixer un jour pour rejouer une date précise — Tabaski, un jour d'août.
        #: Laissé à None, chaque `reset` tire un jour de l'année, ce qui force la
        #: politique à tenir les trois régimes au lieu d'un seul.
        jour_fixe: int | None = None,
        #: À False, la récompense lit la moyenne des quartiers au lieu du plus
        #: mal servi. Sert uniquement à l'ablation d'équité : c'est la version
        #: du problème que la littérature optimise, et celle qu'on veut battre.
        equite: bool = True,
        #: Tirer la crédibilité de départ à chaque épisode. **À activer pour
        #: entraîner, à laisser fermé pour mesurer.** Voir `reset`.
        confiance_tiree: bool = False,
        #: Le prix de l'énergie ici. La physique — kWh, litres, kg de CO₂ — ne
        #: dépend pas du lieu ; la facture, si. Voir `tarifs.py`.
        tarif: Tarif = TARIF_OUAGA,
    ) -> None:
        super().__init__()
        self.profils = profils
        self.n_zones = len(profils)
        self.regime_force = REGIMES[regime] if isinstance(regime, str) else regime
        self.regime = self.regime_force or SAISON_CHAUDE
        self.cout_passer_la_main = cout_passer_la_main
        self.equite = equite
        self.confiance_tiree = confiance_tiree
        self.tarif = tarif
        self.prix = tarif.prix_locaux()
        #: kWh consommés par source dans la journée. C'est l'unité qui se lit
        #: partout : deux villes ne partagent pas un tarif, elles partagent un
        #: kilowattheure.
        self.kwh = {s: 0.0 for s in SOURCES}
        self.climat = climat
        self.jour_fixe = jour_fixe
        self.jour: Journee = journee(0, climat)

        #: La crédibilité **ne se remet pas à zéro** entre deux journées, et
        #: c'est volontaire : une réputation se construit sur des semaines. Elle
        #: est donc un état de l'environnement qui survit au `reset`, et elle est
        #: donnée à l'agent dans l'observation pour que le problème reste
        #: markovien. Les journées sont couplées par cette variable — c'est une
        #: propriété du problème réel, pas un défaut du simulateur.
        self.credit = Crediteur()
        self.coupures: list[bool] = []

        #: Ce que la ville a déjà mis de côté chez elle, 0 = bidons vides,
        #: 1 = pleins. Contrairement à la crédibilité, ce stock **se vide dans la
        #: journée** : il est physique, pas social.
        self.bidons = 0.0
        #: Alertes qui n'ont presque rien déplacé parce que les bidons étaient
        #: déjà pleins. Compté séparément pour pouvoir le dire.
        self.alertes_sans_effet = 0

        self.rng = np.random.default_rng(seed)
        self.reseau = Reseau(self.regime, self.rng)

        self.zones: list[Zone] = []
        self.heure = 0
        self.carburant = CARBURANT_JOUR
        self.solaire_stocke = 0.0
        self.solaire_bu = 0.0
        self.journal: list[dict] = []

        # deux valeurs par zone (puissance, source), puis passer la main, puis
        # alerter la ville — la seule action qui ne touche aucune pompe
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(2 * self.n_zones + 2,), dtype=np.float32
        )
        # remplissages + demande prévue (zones × jalons) + heure, soleil, réseau,
        # gasoil + prévision de coupure + les deux grandeurs du jour + crédibilité
        #
        # Les deux dernières sont indispensables : la prévision de demande est
        # normalisée, elle porte la *forme* de la journée et pas son *niveau*.
        # Sans elles, l'agent ne peut pas savoir qu'on est à Tabaski.
        taille = self.n_zones * (1 + len(JALONS)) + 4 + HORIZON_RESEAU + 4
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(taille,), dtype=np.float32
        )

    # ------------------------------------------------------------------ état

    def _observation(self) -> np.ndarray:
        valeurs: list[float] = [z.remplissage for z in self.zones]
        for zone in self.zones:
            fenetre = prevision(zone.profil, self.heure, HORIZON_DEMANDE + 1)
            valeurs.extend(float(fenetre[j]) for j in JALONS)
        valeurs.extend(
            [
                self.heure / HEURES,
                solaire_horaire(self.heure) * self.jour.ensoleillement,
                1.0 if self.reseau.disponible(self.heure) else 0.0,
                self.carburant / CARBURANT_JOUR,
                *self.reseau.prevision(self.heure, HORIZON_RESEAU),
                # le jour : combien de soleil, et combien de soif
                self.jour.ensoleillement,
                # 1,0 à 1,83 sur l'année ramené dans [0,1]
                min(1.0, (self.jour.multiplicateur - 1.0) / 1.0),
                # ce qu'il reste de crédit auprès de la ville : sans cette
                # valeur, l'agent alerterait sans savoir si on l'écoute encore.
                # Ramenée de [-1, 1] à [0, 1] : la moitié basse est la zone de
                # défiance, où plus personne ne répond mais où l'on continue de
                # creuser. L'agent doit voir la profondeur du trou, pas seulement
                # qu'il y est — sans quoi il ne peut pas savoir ce que remonter
                # lui coûtera.
                (self.credit.confiance + 1.0) / 2.0,
                # et ce que la ville a déjà en réserve chez elle : sans cette
                # valeur, l'agent ne peut pas savoir qu'une annonce de plus ne
                # servirait à rien, et le problème cesserait d'être markovien
                self.bidons,
            ]
        )
        return np.array(valeurs, dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            self.reseau.rng = self.rng

        # quel jour de l'année on rejoue : fixé, ou tiré. Tiré par défaut, sans
        # quoi la politique n'apprend qu'un seul des trois régimes.
        n = self.jour_fixe if self.jour_fixe is not None else int(self.rng.integers(0, 365))
        self.jour = journee(n, self.climat)

        # le réseau suit la saison : le délestage dépend du niveau du barrage et
        # de la pointe des climatiseurs, donc du même calendrier que la demande
        self.regime = self.regime_force or REGIME_PAR_SAISON[self.jour.saison]
        self.reseau.regime = self.regime

        self.heure = 0
        self.journal = []
        self.coupures = []
        self.credit.en_attente.clear()
        # les bidons, eux, se vident : la ville recommence la journée à sec,
        # contrairement à la confiance qu'elle garde d'un jour sur l'autre
        self.bidons = 0.0

        if self.confiance_tiree and self.rng.random() < PART_REDEMARRAGE:
            # Une journée sur dix, la régie hérite d'une autre réputation.
            #
            # Le reste du temps la confiance persiste, et c'est **le** point : si
            # elle repartait à neuf chaque matin, l'agent ne verrait jamais que
            # le bavardage d'aujourd'hui rend l'alerte inutile demain. Il subit
            # donc ses propres choix sur des séries de plusieurs journées, ce que
            # `truncated` dans `step` rend visible à la fonction de valeur.
            #
            # Le redémarrage occasionnel n'est pas une commodité : sans lui, un
            # agent tombé au plancher de défiance dans ses premiers épisodes y
            # resterait pour tout l'entraînement, l'alerte n'aurait plus aucun
            # effet, donc plus aucun gradient, et il n'apprendrait jamais à s'en
            # servir. Mesuré : plancher atteint au septième jour, puis trois
            # alertes par jour dans le vide pendant trois cent cinquante-huit
            # journées. Un changement de direction à la régie, une ville qui
            # oublie — l'histoire est plausible, et surtout elle garantit que
            # toute la gamme de crédibilité reste visitée.
            self.credit.confiance = float(self.rng.uniform(-0.4, 0.95))
        self.carburant = CARBURANT_JOUR
        self.solaire_stocke = 0.0
        self.solaire_bu = 0.0
        #: Le creux réel de la journée, et non le niveau au moment où l'on
        #: regarde. `pire_remplissage` se lit à minuit, quand tout le monde a
        #: fini de boire : il dit combien de réserve reste au matin, pas à quel
        #: point on est passé près de la panne. Les deux sont utiles et se
        #: lisent à l'envers l'un de l'autre — une cuve pleine à minuit peut
        #: avoir frôlé le vide à 19 h.
        self.creux = 1.0
        self.reseau.nouvelle_journee()

        self.zones = []
        for profil in self.profils:
            #: La cuve tient un tiers de la journée. Assez pour lisser un pic,
            #: pas assez pour ignorer le délestage — c'est ce qui force l'agent
            #: à choisir quand remplir plutôt qu'à remplir tout le temps.
            #:
            #: Elle est dimensionnée sur la demande **de référence**, jamais sur
            #: celle du jour : une cuve est du béton, elle ne grandit pas pour
            #: Tabaski. C'est exactement ce qui rend les jours de fête durs.
            reference = profil.volume_horaire()
            capacite = float(reference.sum()) / 2.5
            debit = float(reference.max()) * MARGE_POMPE

            courbe = profil.courbe()
            if self.jour.ramadan:
                courbe = deformation_ramadan(courbe)
            horaire = courbe / courbe.sum() * float(reference.sum()) * self.jour.multiplicateur

            self.zones.append(
                Zone(
                    profil=profil,
                    capacite=capacite,
                    volume=capacite * 0.55,
                    puissance_kw=debit / RENDEMENT_POMPE,
                    horaire=horaire,
                )
            )
        return self._observation(), {}

    # ------------------------------------------------------------------ pas

    def step(self, action: np.ndarray):
        action = np.asarray(action, dtype=np.float32).clip(0.0, 1.0)
        heure = self.heure

        passe_la_main = bool(action[-2] > 0.5)
        alerte = bool(action[-1] > 0.5)
        if passe_la_main:
            puissances = consigne_exploitant(heure, self.n_zones)
            choix = np.ones(self.n_zones, dtype=int)  # l'exploitant n'arbitre pas
        else:
            puissances = action[0 : 2 * self.n_zones : 2]
            choix = np.minimum((action[1 : 2 * self.n_zones : 2] * 3).astype(int), 2)

        reseau_up = self.reseau.disponible(heure)
        self.coupures.append(not reseau_up)
        # juger les alertes dont la fenêtre s'est refermée avant d'en lancer une
        # nouvelle : on ne s'accorde pas de crédit sur une promesse en cours
        confiance_avant = self.credit.confiance
        self.credit.verifier(heure, self.coupures)

        if alerte:
            # une annonce ne remplit que les récipients encore vides. Crier une
            # seconde fois pendant que la ville a déjà fait ses réserves ne
            # déplace rien de plus, et se juge exactement pareil.
            part = self.credit.alerter(heure) * (1.0 - self.bidons)
            if part < 0.05:
                self.alertes_sans_effet += 1
            self.bidons = min(1.0, self.bidons + part)
            for zone in self.zones:
                zone.horaire = deplacer_demande(zone.horaire, heure, part)

        # la cloche du jour, rabotée par la saison : un ciel d'août rend 21 % de
        # moins qu'un ciel de février, et jusqu'à six fois moins un jour couvert
        soleil = solaire_horaire(heure) * self.jour.ensoleillement
        pointe = 18 <= heure <= 22

        cout = 0.0
        gaspille = 0.0

        for i, zone in enumerate(self.zones):
            puissance = float(puissances[i])
            source = SOURCES[int(choix[i])]
            energie = puissance * zone.puissance_kw

            rendement = 1.0
            if source == "solaire":
                rendement = min(1.0, soleil / 0.2) if soleil > 0 else 0.0
                if rendement == 0.0:
                    gaspille += energie
                else:
                    self.solaire_stocke += energie * rendement
                    self.kwh["solaire"] += energie * rendement
            elif source == "reseau":
                if reseau_up:
                    cout += energie * (
                        self.prix["reseau_pointe"] if pointe else self.prix["reseau"]
                    )
                    self.kwh["reseau"] += energie
                else:
                    rendement = 0.0
                    gaspille += energie
            else:
                servi = min(energie, self.carburant)
                if servi <= 0.0 or energie <= 0.0:
                    rendement = 0.0
                else:
                    rendement *= servi / energie
                    self.carburant -= servi
                    cout += servi * self.prix["diesel"]
                    self.kwh["diesel"] += servi

            zone.remplir(energie * rendement * RENDEMENT_POMPE, solaire=(source == "solaire"))

        # puis la ville boit
        demande_totale = 0.0
        for zone in self.zones:
            besoin = float(zone.horaire[heure])
            demande_totale += besoin
            self.solaire_bu += zone.servir(besoin)

        # après avoir servi : c'est là que la cuve est au plus bas de l'heure
        self.creux = min(self.creux, min(z.remplissage for z in self.zones))

        # les bidons se vident au rythme où l'on avait avancé la consommation :
        # six heures après l'annonce, la maison est de nouveau à sec et une
        # nouvelle annonce reprend tout son effet
        self.bidons = max(0.0, self.bidons - 1.0 / VIDAGE_BIDONS)

        # solder avant de calculer la récompense, et non après : sinon les
        # alertes des quatre dernières heures sont jugées une fois la facture
        # émise, et l'agent apprend à bavarder à partir de 20 h en sachant qu'il
        # ne sera pas payé pour. Une promesse non tenue le reste, même si la
        # journée s'achève avant la fenêtre de jugement.
        if heure + 1 >= HEURES:
            self.credit.solder(self.coupures)

        recompense = self._recompense(cout, gaspille, passe_la_main)
        recompense += self._prix_du_credit(confiance_avant, self.credit.confiance)
        self.journal.append(
            {
                "heure": heure,
                "reseau": reseau_up,
                "soleil": round(soleil, 2),
                "passe_la_main": passe_la_main,
                "sources": [SOURCES[int(c)] for c in choix],
                "puissances": [round(float(p), 2) for p in puissances],
                "remplissages": [round(z.remplissage, 2) for z in self.zones],
                "part_solaire": [round(z.part_solaire, 2) for z in self.zones],
                "cout": round(cout),
                "recompense": round(recompense, 2),
                # la parole : sans ces deux lignes, la nouveauté du projet est
                # invisible dans tout ce qui rejoue une journée
                "alerte": alerte,
                "confiance": round(self.credit.confiance, 3),
                "bidons": round(self.bidons, 3),
                "besoins": [round(float(z.horaire[heure]), 2) for z in self.zones],
            }
        )

        self.heure += 1

        # **Minuit n'est pas une fin du monde, c'est une coupure de mesure.**
        #
        # Renvoyer `terminated=True` à la fin de la journée dit à l'agent que
        # l'avenir ne vaut rien après 23 h. Tant qu'il n'existait que des cuves,
        # c'était sans conséquence : elles repartent pleines. Mais la crédibilité
        # traverse les journées, et sous `terminated` l'agent n'avait aucune
        # raison d'en prendre soin — mesuré, il tombait au plancher de défiance
        # au septième jour et continuait d'émettre trois alertes par jour dans le
        # vide pendant les trois cent cinquante-huit suivants.
        #
        # `truncated` fait amorcer la valeur de l'état suivant par SB3 au lieu de
        # la mettre à zéro. Le coût de demain redevient visible aujourd'hui. Ce
        # n'est pas un réglage : c'est la bonne façon de dire qu'une régie
        # continue d'exister le lendemain.
        tronque = self.heure >= HEURES
        return self._observation(), recompense, False, tronque, self._info()

    def _recompense(self, cout: float, gaspille: float, passe_la_main: bool) -> float:
        """Le quartier le plus mal servi décide, pas la moyenne.

        `min` et non `mean`, et c'est une ligne qui porte tout : avec la moyenne,
        assécher un quartier pour en garder deux pleins est une bonne politique.

        `equite=False` bascule sur la moyenne. Ce n'est pas une option offerte à
        l'utilisateur, c'est l'ablation qui prouve que la ligne sert à quelque
        chose : deux agents, mêmes graines, même tout, une seule différence.
        """
        remplissages = [z.remplissage for z in self.zones]
        pire = min(remplissages) if self.equite else sum(remplissages) / len(remplissages)

        r = 12.0 * pire
        if pire < 0.10:
            r -= 60.0
        elif pire < 0.20:
            r -= 15.0

        #: Le plancher de sécurité, et il vient d'une mesure.
        #:
        #: Sans lui, l'agent apprend à faire tourner les cuves à 0,18 de
        #: remplissage quand les règles écrites tiennent 0,66. Sur la moyenne il
        #: a raison : même service, 40 % moins cher. Le coussin des règles est
        #: effectivement du gaspillage — la plupart du temps.
        #:
        #: Mais « la plupart du temps » n'est pas ce qu'un exploitant achète. À
        #: 0,18 il ne reste rien pour une coupure plus longue que la prévision,
        #: et la prévision est mauvaise exactement les jours où ça compte. Le
        #: coussin n'est pas une inefficacité, c'est une prime d'assurance, et
        #: l'agent ne pouvait pas la voir parce que rien dans la récompense ne
        #: parlait du pire jour.
        #:
        #: Ce terme est ce prix-là, écrit noir sur blanc.
        if pire < RESERVE_MINIMALE:
            r -= 25.0 * (RESERVE_MINIMALE - pire) / RESERVE_MINIMALE

        r -= cout / 1000.0
        r -= gaspille / 40.0  # pomper dans le vide : de l'énergie et rien au bout
        if passe_la_main:
            r -= self.cout_passer_la_main
        return float(r)

    def _prix_du_credit(self, avant: float, apres: float) -> float:
        """Facturer la crédibilité gagnée ou perdue à l'heure où elle bouge.

        Sans ce terme l'agent ne peut pas apprendre à se taire, et ce n'est pas
        un défaut d'entraînement : **la confiance se construit sur des semaines
        et l'horizon d'escompte couvre une journée**. Le coût d'une fausse alerte
        tombe hors de vue de l'agent, qui bavarde donc jusqu'à ce que la ville
        cesse de l'écouter. Mesuré : 7,3 alertes par jour, confiance à 0,00, et
        un canal d'alerte devenu inutile.

        La forme est celle du *potential-based reward shaping* de Ng, Harada et
        Russell (1999), avec `Φ = prix × confiance` — mais **la variante non
        escomptée `Φ(s') − Φ(s)`, et le choix est délibéré.**

        La forme théorique `γ·Φ(s') − Φ(s)` facture à chaque pas un loyer
        `(1−γ)·Φ` pour la simple détention du potentiel. Mesuré ici : une journée
        sans la moindre alerte coûte −10,6, et une régie à qui la ville fait
        pleinement confiance paie deux fois plus qu'une régie discréditée. Dans
        un cadre épisodique où la confiance traverse les épisodes et où la valeur
        est tronquée à la fin de journée, ce loyer n'est jamais compensé par le
        futur : le shaping se met à **récompenser la destruction de sa propre
        réputation**. L'invariance de Ng vaut pour le retour infini, pas pour ce
        découpage-là.

        La différence simple n'a pas ce défaut : elle vaut zéro quand rien ne
        bouge, −6 pour une fausse alerte, +1,6 pour une alerte juste et inédite.
        C'est de la comptabilité — on impute la dépréciation d'un actif à la
        période où elle survient — et le seuil au-dessus duquel il vaut mieux
        parler reste celui qu'impose l'asymétrie `MONTEE`/`CHUTE`, soit 78,9 %
        de justesse, quel que soit le prix choisi. Le prix ne déplace pas
        l'optimum ; il le rend visible dans l'horizon de l'agent.
        """
        return PRIX_CONFIANCE * (apres - avant)

    def _info(self) -> dict:
        bu = sum(float(z.horaire.sum()) for z in self.zones)
        return {
            "pire_remplissage": min(z.remplissage for z in self.zones),
            #: le point le plus bas atteint dans la journée, toutes zones
            #: confondues : la marge qui restait au pire moment
            "creux_journee": self.creux,
            #: de quel jour de l'année il s'agissait, pour pouvoir agréger les
            #: résultats par saison plutôt que sur une moyenne qui les mélange
            "jour": self.jour.jour,
            "saison": self.jour.saison,
            "temperature": self.jour.temperature,
            "evenement": self.jour.evenement,
            #: l'alerte : combien de fois l'agent a parlé, combien de fois il
            #: avait raison, et ce qu'il lui reste de crédit
            "alertes": self.credit.alertes,
            "alertes_justes": self.credit.justes,
            "justesse_alertes": self.credit.justesse,
            "confiance": self.credit.confiance,
            #: les annonces tombées dans le vide, bidons déjà pleins
            "alertes_sans_effet": self.alertes_sans_effet,
            #: l'énergie par source, en kWh — l'unité qui se lit partout, et la
            #: seule dont on puisse tirer un coût dans n'importe quelle monnaie
            "kwh": dict(self.kwh),
            "devise": self.tarif.symbole,
            "heures_a_sec": sum(z.heures_a_sec for z in self.zones),
            "litres_manquants": sum(z.litres_manquants for z in self.zones),
            "heures_coupees": self.reseau.heures_coupees,
            "mains_rendues": sum(1 for e in self.journal if e["passe_la_main"]),
            "cout_total": sum(e["cout"] for e in self.journal),
            "carburant_restant": self.carburant,
            "solaire_stocke_kwh": self.solaire_stocke,
            #: La part de l'eau réellement bue qui avait été pompée au soleil.
            #: C'est le chiffre de la batterie virtuelle : combien de kWh de
            #: lithium n'ont pas eu besoin d'exister.
            "part_solaire_bue": self.solaire_bu / bu if bu > 0 else 0.0,
        }

    def render(self) -> None:
        if not self.journal:
            return
        e = self.journal[-1]
        etat = "réseau" if e["reseau"] else "COUPÉ "
        main = "  (main rendue)" if e["passe_la_main"] else ""
        print(
            f"{e['heure']:02d}h {etat} soleil {e['soleil']:.2f}  "
            f"cuves {e['remplissages']}  solaire {e['part_solaire']}  "
            f"{e['cout']:>6} FCFA{main}"
        )
