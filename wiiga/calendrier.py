"""L'année : la chaleur, la pluie, le soleil, et les fêtes.

Une journée moyenne n'existe pas à Ouagadougou. Entre le 15 avril et le 15 août
la ville change de problème, et une politique qui tient l'un échoue sur l'autre.

**En avril il fait 39,8 °C.** La demande grimpe d'un quart sur les mêmes pompes,
et c'est la pleine saison de délestage. Mais le ciel est dégagé, donc la cuve-
batterie fonctionne : on remplit à midi pour le pic de 19 h.

**En août il fait 30,1 °C et il tombe 8,7 mm par jour.** La demande retombe,
mais l'ensoleillement chute de 21 % en moyenne - et jusqu'à 4,1 MJ/m² sur une
journée couverte contre 25,5 au plus clair. La batterie virtuelle s'effondre au
moment où l'on aurait pu s'en passer, et redevient indispensable quand elle
marche le mieux.

C'est cette inversion qui rend l'apprentissage nécessaire : aucune consigne fixe
ne tient les deux régimes, parce qu'ils demandent des politiques opposées.

Les climatologies sont **mesurées**, pas inventées : moyennes 2023-2025 de
l'archive Open-Meteo pour 12,37 N, 1,53 O. Les dates de fêtes 2026 sont celles
retenues au Burkina.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

# --------------------------------------------------------------------- climat

#: Températures maximales moyennes par mois, °C. Ouagadougou, 2023-2025.
TMAX_OUAGA = (33.3, 35.9, 39.4, 39.8, 38.3, 35.2, 31.6, 30.1, 31.1, 34.5, 35.3, 33.4)

#: Rayonnement solaire quotidien moyen par mois, MJ/m². Même source, même
#: période. C'est ce qui pilote la puissance disponible à la pompe solaire.
SOLEIL_OUAGA = (21.0, 22.5, 22.2, 22.4, 21.7, 20.7, 19.1, 17.8, 19.9, 21.0, 20.8, 20.0)

#: Pluie quotidienne moyenne par mois, mm. Sert au réalisme du récit et à la
#: variabilité du solaire : une journée d'août est nuageuse ou ne l'est pas.
PLUIE_OUAGA = (0.0, 0.0, 0.28, 0.01, 0.94, 2.77, 5.34, 8.74, 6.07, 1.15, 0.0, 0.0)


@dataclass(frozen=True)
class Climat:
    """La climatologie d'une ville, douze valeurs par grandeur.

    Séparé du reste pour qu'une autre ville se branche sans toucher au modèle :
    c'est le point d'entrée par lequel `wiiga.ville` fait entrer n'importe quel
    point du globe, et le seul.
    """

    nom: str
    tmax: tuple[float, ...] = TMAX_OUAGA
    soleil: tuple[float, ...] = SOLEIL_OUAGA
    pluie: tuple[float, ...] = PLUIE_OUAGA
    #: Négatif dans l'hémisphère sud : les saisons s'inversent, et la demande
    #: avec elles. Sydney a son pic de chaleur en janvier.
    latitude: float = 12.37
    #: Le calendrier social voyage avec la ville, parce qu'il ne se déduit pas
    #: du climat. Vide par défaut pour une ville rapatriée : aucune API météo ne
    #: sait quand tombe la Tabaski, et inventer des fêtes serait pire que de
    #: n'en avoir aucune.
    fetes: tuple[Fete, ...] = ()

    def mois(self, jour: int) -> int:
        """Le mois (0-11) d'un jour de l'année (0-364), approximation à 30,4 j."""
        return min(11, int(jour / 30.44))

    def temperature(self, jour: int) -> float:
        """Interpolation entre les moyennes mensuelles, pour éviter les marches."""
        position = jour / 30.44
        m = int(position) % 12
        suivant = (m + 1) % 12
        t = position - int(position)
        return self.tmax[m] * (1 - t) + self.tmax[suivant] * t

    def _interpole(self, valeurs: tuple[float, ...], jour: int) -> float:
        position = jour / 30.44
        m = int(position) % 12
        t = position - int(position)
        return valeurs[m] * (1 - t) + valeurs[(m + 1) % 12] * t

    def ensoleillement(self, jour: int) -> float:
        """Facteur solaire du jour, 1,0 = la meilleure moyenne mensuelle de l'année."""
        return self._interpole(self.soleil, jour) / max(self.soleil)

    def pluviometrie(self, jour: int) -> float:
        """Millimètres attendus ce jour-là, en moyenne."""
        return self._interpole(self.pluie, jour)


#: Défini plus bas, une fois les fêtes déclarées : Ouagadougou est la seule ville
#: dont on connaisse le calendrier social, et c'est ce qui la distingue d'une
#: ville simplement rapatriée par `wiiga.ville`.
OUAGADOUGOU: Climat


# ------------------------------------------------------------------ la demande

#: Au-dessus de ce seuil, chaque degré supplémentaire fait boire davantage.
#: En dessous, la consommation ne descend plus : on boit, on cuisine et on se
#: lave quoi qu'il arrive.
SEUIL_CONFORT = 30.0

#: Part de demande ajoutée par degré au-dessus du seuil.
#:
#: C'est l'hypothèse la moins solide du modèle, et elle est écrite ici plutôt
#: que cachée dans une constante. La littérature sur l'élasticité thermique de
#: la demande d'eau donne 1 à 4 % par °C en climat chaud ; 2,5 % est au milieu.
#: Entre août (30,1 °C) et avril (39,8 °C), cela fait **un quart de demande en
#: plus** sur les mêmes pompes, ce qui correspond à ce que rapportent les régies
#: sahéliennes en saison chaude.
ELASTICITE_PAR_DEGRE = 0.025


def multiplicateur_chaleur(temperature: float) -> float:
    """De combien la chaleur du jour gonfle la demande."""
    return 1.0 + ELASTICITE_PAR_DEGRE * max(0.0, temperature - SEUIL_CONFORT)


# -------------------------------------------------------------------- les fêtes


@dataclass(frozen=True)
class Fete:
    """Un jour où la ville consomme autrement."""

    nom: str
    jour: date
    #: Multiplicateur sur le volume de la journée.
    ampleur: float
    #: Combien de jours avant la fête la préparation commence déjà à peser.
    veille: int = 0


#: Dates 2026 au Burkina Faso. Les fêtes musulmanes suivent le calendrier
#: lunaire et se décalent d'environ onze jours par an : elles sont à remettre à
#: jour chaque année, et c'est pour cela qu'elles sont des dates et non des
#: numéros de jour.
FETES_2026 = (
    Fete("Nouvel An", date(2026, 1, 1), 1.15),
    #: Tabaski est le pic de l'année : abattage, lavage, invités. Deux jours de
    #: préparation qui pèsent déjà.
    Fete("Tabaski", date(2026, 5, 27), 1.60, veille=2),
    Fete("Aïd el-Fitr", date(2026, 3, 21), 1.35, veille=1),
    Fete("Fête de l'indépendance", date(2026, 8, 5), 1.20),
    Fete("Proclamation de la République", date(2026, 12, 11), 1.15),
    Fete("Noël", date(2026, 12, 25), 1.20, veille=1),
)

OUAGADOUGOU = Climat(nom="Ouagadougou", fetes=FETES_2026)

#: Le Ramadan ne gonfle pas la demande, il la déplace. On ne boit pas le jour,
#: et tout se passe entre la rupture du jeûne et la nuit. Le volume total change
#: peu ; l'heure du pic change beaucoup, et c'est bien plus difficile pour
#: l'agent qu'une simple hausse.
RAMADAN_2026 = (date(2026, 2, 19), date(2026, 3, 19))


def _jour_vers_date(jour: int, annee: int = 2026) -> date:
    return date(annee, 1, 1) + timedelta(days=int(jour) % 365)


def evenement(
    jour: int, annee: int = 2026, fetes: tuple[Fete, ...] = FETES_2026
) -> tuple[float, str | None]:
    """Le multiplicateur de la journée et le nom de ce qui s'y passe.

    Le calendrier est un paramètre : une ville rapatriée par `wiiga.ville` arrive
    sans fêtes, parce qu'aucune source météo ne sait quand tombe la Tabaski.
    """
    d = _jour_vers_date(jour, annee)
    for f in fetes:
        if d == f.jour:
            return f.ampleur, f.nom
        if f.veille and 0 < (f.jour - d).days <= f.veille:
            # la préparation pèse la moitié de la fête elle-même
            return 1.0 + (f.ampleur - 1.0) * 0.5, f"veille de {f.nom}"
    return 1.0, None


def en_ramadan(jour: int, annee: int = 2026) -> bool:
    debut, fin = RAMADAN_2026
    return debut <= _jour_vers_date(jour, annee) <= fin


def deformation_ramadan(courbe: np.ndarray) -> np.ndarray:
    """Déplacer la demande du jour vers la rupture du jeûne.

    On enlève de la masse entre 6 h et 17 h, on la remet entre 18 h et 22 h. Le
    volume total est conservé : c'est un déplacement, pas une hausse.
    """
    c = courbe.astype(np.float64).copy()
    heures = np.arange(24)
    jour = (heures >= 6) & (heures <= 17)
    soir = (heures >= 18) & (heures <= 22)

    deplace = c[jour].sum() * 0.35
    c[jour] *= 0.65
    c[soir] += deplace * (c[soir] / c[soir].sum())
    return c


# --------------------------------------------------------------------- l'année


@dataclass
class Journee:
    """Tout ce que le calendrier dit d'un jour donné."""

    jour: int
    temperature: float
    ensoleillement: float
    pluie: float
    multiplicateur: float
    evenement: str | None
    ramadan: bool

    #: Les seuils du lieu, posés par `journee()`. Une saison n'a de sens que
    #: relativement à la ville qui la vit.
    seuil_pluie: float = 1.0
    seuil_soleil: float = 1.0
    seuil_chaleur: float = 37.0

    @property
    def saison(self) -> str:
        """Trois régimes, parce que le problème en change trois fois par an.

        La pluie décide en premier, et non l'ensoleillement : septembre reçoit
        6 mm par jour tout en gardant un ciel correct, et le classer « sec »
        parce que le soleil revient serait faux pour quiconque vit là.

        **Les seuils sont ceux de la ville, pas des constantes.** Une première
        version comparait à 1 mm/j et 37 °C, chiffres lus sur Ouagadougou où la
        saison sèche reçoit exactement 0,0 mm. Branchée sur Sydney, elle
        annonçait 365 jours de saison des pluies : une ville tempérée reçoit de
        la pluie toute l'année sans avoir de mousson pour autant. Un tiers
        supérieur de la distribution locale dit ce qu'un seuil universel ne peut
        pas dire - qu'une saison est un **écart à la normale du lieu**.
        """
        if self.pluie >= self.seuil_pluie and self.ensoleillement < self.seuil_soleil:
            return "pluies"
        if self.temperature >= self.seuil_chaleur:
            return "sèche chaude"
        return "sèche tempérée"


@lru_cache(maxsize=32)
def seuils(climat: Climat) -> tuple[float, float, float]:
    """Où passent, pour cette ville-là, la saison des pluies et la saison chaude.

    Deux conditions pour la saison des pluies, et il en faut deux.

    Le **rang** d'abord : le tiers le plus arrosé de l'année localement, ce qui
    évite de comparer Ouagadougou à Chennai avec la même règle. Mais le rang seul
    ne dit rien - un tiers d'une année en est toujours un tiers, et découper par
    quantile donnait exactement 122 jours de « pluies » à Ouagadougou, à Sydney
    et à Nairobi. Un chiffre identique partout est un chiffre qui ne mesure rien.

    Le **ciel** ensuite, et c'est lui qui porte le sens physique : ce que le
    simulateur reproche à la saison des pluies n'est pas d'être humide, c'est de
    couvrir le ciel et de faire tomber la pompe solaire au moment où l'on
    comptait dessus. Un jour n'entre donc dans la saison des pluies que s'il est
    à la fois arrosé et **moins ensoleillé que la moyenne de sa ville**. Sydney
    reçoit sa pluie la plus forte en janvier, sous 22,4 MJ/m² de soleil : c'est
    un orage d'été, pas une mousson, et la cuve-batterie s'en moque.

    Le plancher à 0,5 mm est la seule valeur absolue, pour un cas précis : dans
    une ville aride le tiers le plus arrosé peut être à 0,1 mm/j, ce qui n'est
    pas une saison des pluies mais du bruit de mesure.
    """
    pluies = np.array([climat.pluviometrie(j) for j in range(365)])
    temperatures = np.array([climat.temperature(j) for j in range(365)])
    soleil = np.array([climat.ensoleillement(j) for j in range(365)])

    seuil_pluie = max(0.5, float(np.quantile(pluies, 2 / 3)))
    seuil_soleil = float(soleil.mean())

    mouillees = (pluies >= seuil_pluie) & (soleil < seuil_soleil)
    # 60ᵉ centile des seuls jours secs : la saison chaude se juge hors mousson,
    # sinon les jours de pluie tièdes déplacent la référence
    seches = temperatures[~mouillees]
    reference = seches if seches.size else temperatures
    return seuil_pluie, seuil_soleil, float(np.quantile(reference, 0.6))


def journee(jour: int, climat: Climat = OUAGADOUGOU, annee: int = 2026) -> Journee:
    """Le portrait complet d'un jour : ce qu'il fait dehors et ce qui s'y fête."""
    seuil_pluie, seuil_soleil, seuil_chaleur = seuils(climat)
    t = climat.temperature(jour)
    ampleur, nom = evenement(jour, annee, climat.fetes)
    return Journee(
        jour=int(jour) % 365,
        temperature=t,
        ensoleillement=climat.ensoleillement(jour),
        pluie=climat.pluviometrie(jour),
        multiplicateur=multiplicateur_chaleur(t) * ampleur,
        evenement=nom,
        # le Ramadan est un fait de calendrier, pas de climat : il ne s'applique
        # qu'aux villes dont on connaît la pratique, donc à celles qui ont un
        # calendrier de fêtes
        ramadan=bool(climat.fetes) and en_ramadan(jour, annee),
        seuil_pluie=seuil_pluie,
        seuil_soleil=seuil_soleil,
        seuil_chaleur=seuil_chaleur,
    )
