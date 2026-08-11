"""Brancher n'importe quelle ville du monde sur le modèle, par son nom.

`Climat` a toujours été le seul point par lequel la géographie entre dans le
simulateur : douze températures, douze ensoleillements, douze pluviométries.
Ce fichier va les chercher pour une ville quelconque au lieu de les avoir codées
en dur, et c'est tout ce qu'il fait. Rien d'autre ne change - ni l'agent, ni la
récompense, ni les pompes.

Deux appels, sans clé d'API et sans compte :

- **le géocodage** traduit « Ouagadougou » en 12,37 N / 1,53 O ;
- **l'archive** rend trois ans de relevés quotidiens à ce point, dont on tire les
  moyennes mensuelles.

Ce sont des **mesures**, pas un modèle climatique : `temperature_2m_max` est ce
qu'ont lu les stations et la réanalyse ERA5 entre 2023 et 2025.

**Le cache est écrit sur disque, et il est fait pour être commité.** Une démo qui
dépend du réseau échoue le jour où on la montre. Une ville déjà consultée se
recharge hors ligne, à l'identique, et le fichier dit de quand il date.

Ce que ce module ne sait pas faire, et qu'il vaut mieux écrire que sous-entendre :
il rapatrie le climat, **pas le calendrier social**. Les fêtes qui déplacent la
demande d'eau - Tabaski, Ramadan - n'existent dans aucune API météo. Une ville
récupérée arrive donc avec ses saisons justes et son calendrier vide, sauf si on
le lui fournit. C'est une limite du monde, pas du code.

Usage : `python -m wiiga.ville Sydney`
"""

from __future__ import annotations

import json
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .calendrier import Climat, Fete

GEOCODAGE = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

#: Trois années pleines : assez pour lisser une saison des pluies faible ou
#: forte, assez peu pour rester dans le climat d'aujourd'hui plutôt que dans
#: celui d'il y a trente ans.
DEBUT, FIN = "2023-01-01", "2025-12-31"

CACHE = Path(__file__).resolve().parent.parent / "villes"

DELAI = 30


@dataclass(frozen=True)
class Lieu:
    """Un point sur la carte, avec de quoi le citer."""

    nom: str
    pays: str
    latitude: float
    longitude: float

    def __str__(self) -> str:
        return f"{self.nom}, {self.pays} ({self.latitude:.2f}, {self.longitude:.2f})"


def _slug(nom: str) -> str:
    """Un nom de fichier stable, sans accent ni espace."""
    plat = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "-" for c in plat.lower()).strip("-")


def _get(url: str, params: dict) -> dict:
    with urllib.request.urlopen(
        url + "?" + urllib.parse.urlencode(params), timeout=DELAI
    ) as r:
        return json.load(r)


def geocoder(nom: str) -> Lieu:
    """Trouver la ville. Le premier résultat, c'est-à-dire la plus peuplée."""
    reponse = _get(GEOCODAGE, {"name": nom, "count": 1, "format": "json"})
    resultats = reponse.get("results")
    if not resultats:
        raise LookupError(f"aucune ville nommée « {nom} »")
    r = resultats[0]
    return Lieu(r["name"], r.get("country", "?"), r["latitude"], r["longitude"])


def _moyennes_mensuelles(dates: list[str], valeurs: list) -> tuple[float, ...]:
    """Douze moyennes, en ignorant les trous de la série."""
    sommes = [0.0] * 12
    comptes = [0] * 12
    for d, v in zip(dates, valeurs):
        if v is None:
            continue
        m = int(d[5:7]) - 1
        sommes[m] += float(v)
        comptes[m] += 1
    manquants = [m + 1 for m, c in enumerate(comptes) if c == 0]
    if manquants:
        raise ValueError(f"aucune donnée pour les mois {manquants}")
    return tuple(s / c for s, c in zip(sommes, comptes))


def relever(lieu: Lieu) -> dict:
    """Trois ans de relevés à ce point, réduits à douze valeurs par grandeur."""
    d = _get(
        ARCHIVE,
        {
            "latitude": lieu.latitude,
            "longitude": lieu.longitude,
            "start_date": DEBUT,
            "end_date": FIN,
            "daily": "temperature_2m_max,shortwave_radiation_sum,precipitation_sum",
            "timezone": "auto",
        },
    )["daily"]

    return {
        "nom": lieu.nom,
        "pays": lieu.pays,
        "latitude": lieu.latitude,
        "longitude": lieu.longitude,
        "tmax": _moyennes_mensuelles(d["time"], d["temperature_2m_max"]),
        "soleil": _moyennes_mensuelles(d["time"], d["shortwave_radiation_sum"]),
        "pluie": _moyennes_mensuelles(d["time"], d["precipitation_sum"]),
        "periode": f"{DEBUT} au {FIN}",
        "source": "Open-Meteo / ERA5, relevés quotidiens",
        "releve_le": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _vers_climat(brut: dict, fetes: tuple[Fete, ...] = ()) -> Climat:
    return Climat(
        nom=brut["nom"],
        tmax=tuple(brut["tmax"]),
        soleil=tuple(brut["soleil"]),
        pluie=tuple(brut["pluie"]),
        latitude=brut["latitude"],
        fetes=fetes,
    )


def climat_de(
    nom: str,
    *,
    hors_ligne: bool = False,
    rafraichir: bool = False,
    fetes: tuple[Fete, ...] = (),
) -> Climat:
    """Le climat d'une ville : du cache si on l'a, du réseau sinon.

    `hors_ligne=True` interdit le réseau - c'est le mode de la démonstration,
    où l'on préfère un échec net à une attente devant un jury.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    fichier = CACHE / f"{_slug(nom)}.json"

    if fichier.exists() and not rafraichir:
        return _vers_climat(json.loads(fichier.read_text(encoding="utf-8")), fetes)

    if hors_ligne:
        connues = sorted(p.stem for p in CACHE.glob("*.json"))
        raise LookupError(
            f"« {nom} » n'est pas en cache et le réseau est interdit. "
            f"Villes disponibles : {', '.join(connues) or 'aucune'}"
        )

    brut = relever(geocoder(nom))
    fichier.write_text(
        json.dumps(brut, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return _vers_climat(brut, fetes)


def _saisons(climat: Climat) -> dict[str, int]:
    """Combien de jours de chaque régime, pour voir d'un coup d'œil la ville."""
    from .calendrier import journee

    compte: dict[str, int] = {}
    for j in range(365):
        s = journee(j, climat).saison
        compte[s] = compte.get(s, 0) + 1
    return compte


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Brancher une ville sur WIIGA.")
    p.add_argument("ville")
    p.add_argument("--hors-ligne", action="store_true")
    p.add_argument("--rafraichir", action="store_true")
    args = p.parse_args()

    try:
        c = climat_de(args.ville, hors_ligne=args.hors_ligne, rafraichir=args.rafraichir)
    except (LookupError, urllib.error.URLError) as e:
        raise SystemExit(f"échec : {e}") from e

    mois = "jan fév mar avr mai jun jul aoû sep oct nov déc".split()
    print(f"\n{c.nom}  ({c.latitude:.2f})")
    print(f"{'':<14}" + "".join(f"{m:>7}" for m in mois))
    for titre, valeurs, unite in (
        ("température", c.tmax, "°C"),
        ("soleil", c.soleil, "MJ/m²"),
        ("pluie", c.pluie, "mm/j"),
    ):
        print(f"{titre + ' ' + unite:<14}" + "".join(f"{v:>7.1f}" for v in valeurs))

    print("\nrégimes sur l'année :")
    for saison, n in sorted(_saisons(c).items(), key=lambda kv: -kv[1]):
        print(f"  {saison:<16}{n:>4} jours")

    if c.latitude < 0:
        print("\nhémisphère sud : le pic de chaleur est en janvier, et l'agent le")
        print("voit dans son observation sans qu'on ait rien à lui dire.")


if __name__ == "__main__":
    main()
