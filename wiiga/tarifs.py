"""Ce que l'énergie coûte, selon l'endroit où l'on est.

Un chiffre en francs CFA se lit à Ouagadougou et nulle part ailleurs. Mais le
réflexe de tout convertir en dollars est une mauvaise réponse à un vrai problème,
parce qu'il déplace la question sans la résoudre : un tarif de l'électricité
change d'un pays à l'autre bien plus qu'un taux de change ne le corrige.

La bonne réponse tient en une phrase : **la physique est universelle, l'argent
est local.** Ce projet mesure donc d'abord en kilowattheures, en litres de
gasoil, en kilos de CO₂ et en personnes-jours au-dessus du seuil de survie — des
unités qui se lisent à Sydney comme à Ouagadougou. Le coût monétaire est une
couche de présentation posée par-dessus, avec le tarif du lieu et la conversion
écrite en clair.

**C'est aussi la seule donnée du projet qui ne se rapatrie pas toute seule.** Le
climat vient d'Open-Meteo sans clé ni compte ; il n'existe pas d'équivalent
ouvert et fiable pour les tarifs de l'électricité ville par ville. Les valeurs
ci-dessous sont donc des **ordres de grandeur déclarés**, pas des relevés, et
elles vivent dans un seul fichier pour qu'une régie qui connaît ses vrais tarifs
les remplace en une minute. Les annoncer pour ce qu'elles sont vaut mieux que de
les faire passer pour mesurées.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Les trois sources, dans l'ordre où `env.SOURCES` les attend.
SOURCES = ("solaire", "reseau", "diesel")


@dataclass(frozen=True)
class Tarif:
    """Le prix de l'énergie en un lieu, et de quoi le lire ailleurs.

    Les prix sont en **dollars par kilowattheure**, parce qu'il faut bien une
    unité commune pour comparer deux villes, et qu'on affiche ensuite dans la
    monnaie locale. Le solaire est à zéro partout : le panneau est déjà posé, et
    son amortissement ne dépend pas de l'heure à laquelle l'agent décide de
    pomper — le mettre dans le coût horaire fausserait précisément l'arbitrage
    qu'on veut mesurer.
    """

    devise: str
    symbole: str
    #: Combien d'unités de monnaie locale pour un dollar.
    par_usd: float
    #: Prix du kWh réseau en heures creuses, USD.
    reseau_usd: float
    #: Prix du kWh réseau en pointe du soir, USD.
    pointe_usd: float
    #: Prix du kWh produit au groupe électrogène, USD. Amortissement du groupe
    #: compris, ce qui explique qu'il coûte plus cher qu'il n'en a l'air à la
    #: pompe à carburant.
    diesel_usd: float

    def local(self, usd: float) -> float:
        return usd * self.par_usd

    def prix_locaux(self) -> dict[str, float]:
        """Le dictionnaire que `env` attend, en monnaie locale."""
        return {
            "solaire": 0.0,
            "reseau": self.local(self.reseau_usd),
            "reseau_pointe": self.local(self.pointe_usd),
            "diesel": self.local(self.diesel_usd),
        }

    def ecrire(self, montant_local: float) -> str:
        """Un montant lisible, monnaie locale et dollars."""
        return f"{montant_local:,.0f} {self.symbole} ({montant_local / self.par_usd:,.0f} USD)"


#: Ouagadougou, tarifs SONABEL indicatifs. Ce sont les valeurs sur lesquelles
#: tous les chiffres du dépôt ont été mesurés — 120, 250 et 400 FCFA le kWh —
#: reconstruites ici en dollars pour que les autres villes s'y comparent.
#:
#: Le franc CFA est arrimé à l'euro à parité fixe (655,957 FCFA pour 1 €), ce qui
#: rend la conversion stable dans le temps, contrairement à la plupart des
#: monnaies de cette table.
OUAGADOUGOU = Tarif(
    devise="XOF",
    symbole="FCFA",
    par_usd=607.0,
    reseau_usd=0.198,
    pointe_usd=0.412,
    diesel_usd=0.659,
)


#: Les autres villes de la démonstration.
#:
#: **Ordres de grandeur, pas relevés.** Les prix résidentiels de l'électricité
#: sont publiés par pays et varient d'un facteur trois entre l'Inde et la France ;
#: on retient une valeur plausible par pays. Les rapports pointe/creux et
#: groupe/réseau sont ceux de Ouagadougou faute de mieux, et c'est écrit ici
#: plutôt que sous-entendu : ce qui voyage d'une ville à l'autre dans ce projet,
#: c'est le climat, qui est mesuré. Le tarif, lui, est à renseigner.
TARIFS = {
    "Ouagadougou": OUAGADOUGOU,
    "Sydney": Tarif("AUD", "A$", 1.52, 0.220, 0.458, 0.733),
    "Paris": Tarif("EUR", "€", 0.92, 0.280, 0.583, 0.933),
    "Budapest": Tarif("HUF", "Ft", 355.0, 0.110, 0.229, 0.367),
    "Chennai": Tarif("INR", "₹", 84.0, 0.080, 0.167, 0.267),
    "Nairobi": Tarif("KES", "KSh", 129.0, 0.200, 0.417, 0.667),
    "Lima": Tarif("PEN", "S/", 3.75, 0.160, 0.333, 0.533),
}

#: Pour une ville dont on ne connaît pas le tarif, on n'invente rien : on prend
#: la médiane mondiale approximative et on le dit. Mieux vaut un chiffre annoncé
#: comme générique qu'un chiffre précis et faux.
DEFAUT = Tarif("USD", "USD", 1.0, 0.150, 0.312, 0.500)


def tarif_de(ville: str) -> tuple[Tarif, bool]:
    """Le tarif d'une ville, et si on le connaît vraiment."""
    t = TARIFS.get(ville)
    return (t, True) if t else (DEFAUT, False)
