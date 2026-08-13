"""Un choc de consommation que rien n'annonce, et ce que chaque politique en fait.

Le README declare que l'elasticite de la demande a la chaleur est l'hypothese la
plus faible du projet. Une hypothese faible qu'on se contente de declarer reste
une hypothese faible ; ce module la transforme en enveloppe mesuree, en posant la
question a l'envers : **de combien le modele de demande peut-il se tromper avant
que l'agent cede ?**

Le cas est reel avant d'etre methodologique. Un dispensaire pris dans une flambee
de paludisme, une ecole qui rouvre, un quartier qui recoit des personnes
deplacees : la consommation d'une zone double ou triple pendant une periode, et
la prevision de la regie continue d'annoncer la courbe habituelle. Ce n'est pas
un cas limite exotique, c'est le quotidien d'une regie sahelienne.

**Le choc est litteralement invisible pour l'agent.** Son observation porte
`prevision(profil, ...)`, c'est-a-dire la *forme normalisee* du profil de la
zone, pas les metres cubes reellement tires. Gonfler `zone.horaire` apres le
`reset` ne change donc aucune valeur de son vecteur d'entree : il ne l'apprend
qu'en voyant ses cuves descendre plus vite que son plan ne le prevoyait. C'est
verifie dans `tests.py` plutot qu'affirme ici, parce que c'est la propriete dont
depend tout ce que ce module pretend mesurer.

Il n'a pas non plus ete entraine la-dessus. Aucun choc n'existe dans
l'environnement d'entrainement : les poids mesures ici sont ceux de
`MODELE_PUBLIE`, geles, exactement ceux de tous les autres tableaux. Ce qu'on
mesure est donc une robustesse qui n'a pas ete demandee, pas une competence
apprise.

Les deux politiques subissent le meme choc, sur les memes journees et les memes
graines. La question n'est pas de savoir laquelle souffre - les deux souffrent -
mais **laquelle se degrade le moins vite**, et a partir de quel facteur l'avance
de l'agent disparait.

Ce qu'on trouve n'est pas ce qu'on cherchait, et c'est le plus interessant :
**l'avance ne disparait pas, parce que la limite n'est pas decisionnelle, elle
est hydraulique.** Sur toute la plage que les pompes peuvent physiquement
absorber, une hausse non annoncee de trente pour cent coute a l'agent deux
centiemes d'heure a sec par jour - une minute - et son avance passe de 53 % a
48 %. Bien avant qu'une erreur de prevision mette l'agent en difficulte, c'est le
debit de la conduite qui sature.

Le module publie donc deux choses, et la seconde vaut peut-etre plus que la
premiere :

- **la conclusion ne bouge pas** quand l'hypothese declaree la plus faible du
  projet se trompe d'un tiers. C'est ce qui repond a l'objection, mesure plutot
  qu'affirme.
- **la marge hydraulique de chaque quartier**, qui est une reponse de planificateur
  au meme titre que les 96 m3 de beton d'`equivalence.py` : le dispensaire tient
  +36 % le jour le plus chaud de l'annee, le marche +54 %, le residentiel +109 %.
  Le plus petit quartier est le plus tendu, et c'est lui qu'il faut agrandir en
  premier.

Execution : `python -m wiiga.choc`
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .baselines import POLITIQUES
from .demande import PROFILS
from .env import MARGE_POMPE, WiigaEnv
from .resultats import LITRES_SURVIE, mesurer

SORTIE = Path(__file__).resolve().parent.parent / "resultats" / "choc.json"

#: Le quartier ou le choc est le plus credible : ecole et dispensaire. C'est
#: aussi le plus petit des trois (4 000 habitants), donc celui dont la cuve
#: absorbe le moins - un choc y fait mal plus vite qu'ailleurs.
ZONE_VEDETTE = 2

#: Les heures ou une ecole et un dispensaire consomment. Un choc nocturne sur ces
#: batiments-la n'aurait pas de sens : ils sont vides.
DEBUT, FIN = 7, 18

#: Le balayage. 1,0 est la reference sans choc - elle doit redonner exactement le
#: tableau annuel, et c'est ce qui prouve que le crochet ne deforme rien tout
#: seul.
#:
#: La borne haute n'est pas un choix de redaction, c'est une limite physique :
#: au-dela du **plafond hydraulique** de la zone, la demande horaire depasse le
#: debit de la pompe et aucune politique ne peut plus servir le quartier. Une
#: premiere version balayait jusqu'a x4 et publiait un agent qui « perd » a x4 -
#: mesure sans objet, puisqu'a x4 le dispensaire reclame 82 m3/h sur une pompe
#: qui en donne 41. On mesurait une conduite trop etroite en croyant mesurer une
#: politique. `plafond_hydraulique` calcule desormais cette borne sur les
#: journees rejouees, et le balayage s'y arrete, en le disant.
#:
#: Les plafonds mesures sur l'annee sont x1,36 pour le dispensaire, x1,54 pour le
#: marche et x2,09 pour le residentiel. Le balayage s'arrete donc a x1,30 : une
#: hausse de trente pour cent de la consommation reelle d'un quartier, que rien
#: n'annonce. C'est modeste dit comme ca, et c'est deja presque tout ce que
#: l'installation peut absorber les jours chauds.
FACTEURS = (1.0, 1.1, 1.2, 1.3)

#: Le facteur auquel les trois quartiers sont compares entre eux : le plus fort
#: qui reste sous le plafond des **trois** zones a la fois. C'est le dispensaire,
#: le plus petit, qui commande.
FACTEUR_COMPARAISON = 1.3


def choc(zone: int, facteur: float, debut: int = DEBUT, fin: int = FIN):
    """Le crochet qui gonfle la demande reelle d'une zone, sans rien annoncer.

    Applique apres `reset`, donc apres que la cuve a ete dimensionnee sur la
    demande de reference : la cuve ne grandit pas parce que le dispensaire a
    plus soif, exactement comme le beton ne grandit pas pour Tabaski.
    """

    def appliquer(env) -> None:
        env.zones[zone].horaire[debut:fin] *= facteur

    return appliquer


def plafond_hydraulique(
    zone: int, journees: int = 365, seed: int = 1000,
    debut: int = DEBUT, fin: int = FIN,
) -> float:
    """Le plus grand facteur que la pompe de cette zone peut encore servir.

    La pompe est dimensionnee sur le pic de la demande de reference, avec une
    marge : `debit = max(reference) * MARGE_POMPE`. Multiplier la demande d'une
    fenetre par `f` multiplie le pic de cette fenetre par `f`. Au-dela du
    rapport entre le debit et ce pic, l'eau ne peut physiquement plus arriver,
    et l'ecart entre deux politiques ne dit plus rien de ces politiques.

    Le pic est cherche sur **les journees que la campagne rejoue**, pas sur le
    profil de reference. La difference n'est pas academique : sur le profil seul,
    le dispensaire semble tenir jusqu'a x2,50 ; sur l'annee, la chaleur et les
    fetes portent son pic de 16,4 a 30,1 m3/h et le plafond tombe a x1,36. Une
    premiere version publiait un balayage jusqu'a x2 en s'appuyant sur la borne
    optimiste - les trois quarts du tableau mesuraient une pompe saturee les
    jours chauds, c'est-a-dire exactement les jours qui comptent.
    """
    reference = PROFILS[zone].volume_horaire()
    debit = float(reference.max()) * MARGE_POMPE

    env = WiigaEnv(seed=0)
    pic = 0.0
    for j in range(journees):
        env.jour_fixe = j % 365
        env.reset(seed=seed + j)
        pic = max(pic, float(env.zones[zone].horaire[debut:fin].max()))
    return debit / pic


def sous_choc(politiques: dict, journees: int, seed: int, crochet) -> dict:
    """Les memes politiques, la meme annee, la meme deformation pour chacune."""
    return {
        nom: mesurer(pol, journees, seed, apres_reset=crochet)
        for nom, pol in politiques.items()
    }


def lignes(mesures: dict, agent_nom: str, regle_nom: str) -> dict:
    """Ce qu'on retient d'une campagne : le service, en heures et en gens."""
    a, r = mesures[agent_nom], mesures[regle_nom]
    ha, hr = a["heures_a_sec_par_jour"], r["heures_a_sec_par_jour"]
    return {
        "agent_heures_a_sec": ha,
        "regle_heures_a_sec": hr,
        "agent_personnes": a["litres_manquants_par_jour"] / LITRES_SURVIE,
        "regle_personnes": r["litres_manquants_par_jour"] / LITRES_SURVIE,
        "ecart_pct": 0.0 if hr == 0 else (hr - ha) / hr * 100.0,
        "agent_creux": a["creux_moyen"],
        "regle_creux": r["creux_moyen"],
    }


def main() -> None:
    from .train import MODELE_PUBLIE

    p = argparse.ArgumentParser()
    p.add_argument("--journees", type=int, default=365)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--modele", default=MODELE_PUBLIE)
    args = p.parse_args()

    from stable_baselines3 import PPO

    from .train import politique_agent

    agent_nom = "agent WIIGA (PPO)"
    regle_nom = "prévoyant (règle écrite)"
    politiques = {
        agent_nom: politique_agent(PPO.load(args.modele)),
        regle_nom: POLITIQUES[regle_nom],
    }

    nom_zone = PROFILS[ZONE_VEDETTE].nom

    # ------------------------------------------------------- ce qui est mesurable
    plafonds = {
        p.nom: plafond_hydraulique(i, args.journees, args.seed)
        for i, p in enumerate(PROFILS)
    }
    print("\nplafond hydraulique par quartier, sur les journees rejouees - au-dela,")
    print("la pompe ne suit plus et l'ecart ne mesure plus les politiques")
    for nom, f in plafonds.items():
        print(f"  {nom:<14} x{f:.2f}")
    trop_haut = [f for f in FACTEURS if f > plafonds[nom_zone] + 1e-9]
    if trop_haut:
        raise SystemExit(
            f"FACTEURS contient {trop_haut}, au-dessus du plafond "
            f"x{plafonds[nom_zone]:.2f} de « {nom_zone} » : refus de publier une "
            f"comparaison qui mesurerait le debit de la pompe."
        )

    # ------------------------------------------------- de combien peut-on se tromper
    print(f"\nchoc sur le quartier « {nom_zone} » (ecole + dispensaire), "
          f"de {DEBUT} h a {FIN} h, {args.journees} journees")
    print(f"{'facteur':>9}{'agent h sec/j':>16}{'regle h sec/j':>16}"
          f"{'ecart':>9}{'agent pers/j':>15}{'regle pers/j':>15}")
    print("-" * 80)

    balayage = []
    for f in FACTEURS:
        crochet = None if f == 1.0 else choc(ZONE_VEDETTE, f)
        L = lignes(sous_choc(politiques, args.journees, args.seed, crochet),
                   agent_nom, regle_nom)
        L["facteur"] = f
        balayage.append(L)
        print(f"{f:>9.2f}{L['agent_heures_a_sec']:>16.2f}"
              f"{L['regle_heures_a_sec']:>16.2f}{L['ecart_pct']:>8.0f}%"
              f"{L['agent_personnes']:>15.0f}{L['regle_personnes']:>15.0f}")

    # La ligne x1,0 doit redonner le tableau annuel au chiffre pres. C'est le
    # controle qui dit que le crochet ne deforme rien par lui-meme : si la
    # reference derivait, tout le reste du tableau mesurerait le crochet au lieu
    # du choc. On le verifie a voix haute plutot que de l'esperer.
    accord = None
    ref = SORTIE.parent / "comparaison.json"
    if ref.exists():
        publie = json.loads(ref.read_text(encoding="utf-8"))["mesures"]
        attendu = publie[agent_nom]["heures_a_sec_par_jour"]
        obtenu = balayage[0]["agent_heures_a_sec"]
        accord = abs(attendu - obtenu) < 1e-9
        print(f"\nreference sans choc : {obtenu:.3f} h a sec/j contre {attendu:.3f} "
              f"dans comparaison.json - {'identique' if accord else 'ECART'}")

    # ------------------------------------------------------- et dans les autres
    print(f"\nle meme choc x{FACTEUR_COMPARAISON:.2f}, quartier par quartier")
    print(f"{'quartier':>14}{'habitants':>11}{'agent h sec/j':>16}"
          f"{'regle h sec/j':>16}{'ecart':>9}")
    print("-" * 66)

    par_quartier = []
    for i, profil in enumerate(PROFILS):
        if FACTEUR_COMPARAISON > plafonds[profil.nom] + 1e-9:
            # jamais silencieusement : une ligne absente d'un tableau doit dire
            # pourquoi elle est absente, sinon elle ressemble a un oubli
            print(f"{profil.nom:>14}{profil.habitants:>11}"
                  f"{'au-dela du plafond x' + format(plafonds[profil.nom], '.2f'):>41}")
            continue
        L = lignes(
            sous_choc(politiques, args.journees, args.seed,
                      choc(i, FACTEUR_COMPARAISON)),
            agent_nom, regle_nom,
        )
        L["zone"] = profil.nom
        L["habitants"] = profil.habitants
        L["plafond_hydraulique"] = plafonds[profil.nom]
        par_quartier.append(L)
        print(f"{profil.nom:>14}{profil.habitants:>11}"
              f"{L['agent_heures_a_sec']:>16.2f}{L['regle_heures_a_sec']:>16.2f}"
              f"{L['ecart_pct']:>8.0f}%")

    # ------------------------------------------------------------ ce qu'on en dit
    #
    # Le chiffre qui compte n'est pas le niveau atteint sous choc : les deux
    # politiques se degradent, et une politique qui se degrade n'est pas une
    # nouvelle. C'est la *vitesse* de degradation, parce qu'elle dit laquelle des
    # deux avait de la marge - et la marge de l'agent vient de la cuve remplie a
    # midi, qui est une reserve qu'il ne s'etait pas constituee pour ca.
    sans = balayage[0]
    # la ligne x1,0 est la reference, pas un choc : la compter parmi les facteurs
    # ou l'agent « cede » ferait dire au resume que l'avantage disparait a x1,0,
    # c'est-a-dire quand il ne se passe rien.
    chocs = [L for L in balayage if L["facteur"] > 1.0]
    gagnes = [L["facteur"] for L in chocs if L["ecart_pct"] > 0]
    perdus = [L["facteur"] for L in chocs if L["ecart_pct"] <= 0]
    tient_jusqua = max(gagnes) if gagnes else None
    cede_a = min(perdus) if perdus else None

    pire = balayage[-1]
    da = pire["agent_heures_a_sec"] - sans["agent_heures_a_sec"]
    dr = pire["regle_heures_a_sec"] - sans["regle_heures_a_sec"]

    if tient_jusqua is None:
        print("\nl'agent ne garde son avantage a aucun facteur de choc mesure")
    elif cede_a is None:
        print(f"\nl'agent garde l'avantage sur toute la plage mesuree, "
              f"jusqu'a x{tient_jusqua:.1f}")
    else:
        print(f"\nl'agent garde l'avantage jusqu'a x{tient_jusqua:.1f}, "
              f"et le perd a x{cede_a:.1f}")

    print(f"a x{pire['facteur']:.2f}, le choc coute {da:+.2f} h a sec par jour a "
          f"l'agent et {dr:+.2f} a la regle")
    # dit dans les deux sens : un rapport de 0,8 annonce comme « plus lent »
    # serait exactement le genre de formulation que le reste du depot s'interdit
    if da > 1e-9 and dr > 1e-9:
        rapport = dr / da
        sens = "moins vite" if rapport > 1 else "plus vite"
        print(f"soit une degradation {max(rapport, 1 / rapport):.1f} fois {sens} "
              f"pour l'agent que pour la regle")
    elif da <= 1e-9:
        print("l'agent ne se degrade pas du tout sur cette plage")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(
            {
                "genere_le": datetime.now(UTC).isoformat(timespec="seconds"),
                "journees": args.journees,
                "seed": args.seed,
                "modele": args.modele,
                "zone_vedette": nom_zone,
                "fenetre_horaire": [DEBUT, FIN],
                "facteur_comparaison": FACTEUR_COMPARAISON,
                "plafonds_hydrauliques": plafonds,
                "balayage": balayage,
                "par_quartier": par_quartier,
                "resume": {
                    "reference_identique_au_tableau_annuel": accord,
                    "tient_jusqua": tient_jusqua,
                    "cede_a": cede_a,
                    "degradation_agent_au_pire": da,
                    "degradation_regle_au_pire": dr,
                    "facteur_au_pire": pire["facteur"],
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\necrit dans {SORTIE}")


if __name__ == "__main__":
    main()
