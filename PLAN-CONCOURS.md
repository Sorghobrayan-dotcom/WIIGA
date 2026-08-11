# WIIGA — plan d'exécution, ML Empowerment Build Challenge 2.0

**Dépôt : 15 août 2026, 6h45 UTC.** Cinq jours.
**Cible : 187 projets l'an dernier, 12 gagnants.** Une chance sur quinze.

Hypothèse de travail : **tous les concurrents valent le vainqueur 2025 ou mieux.**
Donc rien ne se joue sur l'idée. Tout se joue sur la preuve.

---

## Ce qui existe déjà (audit du 10 août)

| Fichier | Ce qu'il apporte | État |
|---|---|---|
| `wiiga/env.py` (388 l.) | Gymnasium, cuve-batterie, réseau qui tombe, « passer la main », **récompense max-min** | solide |
| `wiiga/baselines.py` (130 l.) | `exploitant` (ce qui tourne vraiment) + `moins_cher` (la formulation de la littérature) + `evaluer(200 jours, seed)` | **le harnais existe, jamais publié** |
| `wiiga/demande.py` (92 l.) | profils par zone, OMS 50 L/hab/j | à étendre |
| `wiiga/grid.py` (133 l.) | régimes de délestage, `SAISON_CHAUDE` | base saisonnière présente |
| `wiiga_agent.zip` (177 Ko) | agent entraîné | à réévaluer |
| `demo/index.html` (33 Ko) | planche SVG, rejeu | **pas hébergée** |

**L'équité, le point le plus fort du projet, est déjà codée.** Le vainqueur 2025
a gagné exactement là-dessus, dans un autre domaine.

---

## Les cinq critères, et l'artefact qui coche chacun

Chaque ligne doit être **vraie et vérifiable** le 15 août. Pas une intention.

### Technical Implementation — 30 %

> « L'agent PPO bat `exploitant` de **X %** et `moins_cher` de **Y %** sur
> 200 journées à graines identiques. Tableau publié. »

**Artefact :** `resultats/comparaison.json` + un tableau dans le README.
**Coût : 1 heure.** Le harnais existe. Il n'a jamais tourné pour publier.

C'est le point où le meilleur analogue de l'an dernier a échoué : FUSIONPILOT
admet que son heuristique écrite à la main bat son agent RL. **Si le tien gagne
avec un chiffre, tu as ce qu'aucun des douze n'avait.**

Si l'agent ne bat pas les baselines : on le dit, et on répare. Un chiffre honnête
qui perd vaut mieux qu'un silence.

### Creativity & Innovation — 20 %

> « L'agent a une action non hydraulique : **prévenir**. Alerter coûte de la
> crédibilité, donc il apprend la parcimonie. »

**Artefact :** `alerte ∈ {0,1}` dans l'espace d'action, `confiance ∈ [0,1]` dans
l'état, et une courbe montrant que l'agent alerte **moins souvent mais mieux**
au fil de l'entraînement.

Le mécanisme :

```
si alerte → une fraction p = f(confiance) des foyers remplit ses bidons,
            la demande se déplace hors de la fenêtre de coupure
confiance : alerte suivie d'une vraie coupure  → monte lentement
            alerte sans coupure                → chute vite
```

**Ce qui est nouveau, et je l'ai vérifié :** le « demand response » publié
déplace de la charge industrielle par la tarification. Aucun travail ne modélise
un canal de confiance qui se dégrade quand on en abuse. Le coût de l'action est
**l'efficacité future de cette même action**.

### Real-World Impact — 20 %

> « WIIGA rapporte **N heures-personnes d'accès à l'eau** gagnées, et
> **M personnes** passées au-dessus du seuil OMS qui n'y seraient pas. »

**Artefact :** conversion de `litres_manquants` en unités humaines.
`litres_manquants` existe déjà — il manque la division par le seuil et
l'agrégation par quartier nommé.

Une AUC ne se compare à rien. Un nombre de personnes, si.

### Project Design & UX — 15 %

> « Un juge ouvre une URL et voit l'agent tourner en trente secondes, sans rien
> installer. Il tape une ville, le climat se charge, le comportement change. »

**Artefact :** `demo/index.html` hébergée + sélecteur de ville Open-Meteo.

**Ni MediFairNet ni FUSIONPILOT n'avaient de démo hébergée.** Trente pour cent de
la note — Design plus Présentation — laissés sur la table par les deux meilleurs.

La démo est du HTML statique : **hébergement sans fonction serverless, donc sans
le piège qui nous a coûté Backblaze.** GitHub Pages suffit.

### Presentation & Documentation — 15 %

> « Deux mille mots, chaque section du gabarit Devpost remplie, limites
> comprises. »

**Artefact :** le texte de soumission, écrit **le 13**, pas le 15.

FUSIONPILOT écrit noir sur blanc *« not a real tokamak controller »* et gagne.
Sur ce jury, l'honnêteté se lit comme de la rigueur.

À écrire explicitement : *« PPO for pump scheduling is established work. What is
new here is the objective and the communication action. »*

---

## Les cinq prix visés, et le chiffre qui déclenche chacun

| Prix | Le chiffre |
|---|---|
| **Best Overall** | l'écart mesuré aux deux baselines |
| **Sustainability AI** | **litres de gasoil et kg de CO₂ évités**, plus la part solaire |
| **Most Impactful** | heures-personnes, quartiers nommés, seuil OMS |
| **Most Innovative** | parcimonie des alertes : combien, pour quel gain |
| **Most Scalable** | une ville arbitraire configure le modèle en direct |

Ils ne demandent pas cinq projets. Ils demandent **cinq chiffres différents dans
le même write-up**.

---

## L'ordre des cinq jours

### J1 (10 août) — les chiffres qui existent déjà

1. Lancer `evaluer` sur les trois politiques, 200 journées, graines identiques.
   Écrire `resultats/comparaison.json`.
2. Convertir en unités humaines : heures-personnes, personnes sous le seuil OMS.
3. Comptabiliser le gasoil : kWh → litres → kg CO₂ (2,68 kg/L).
4. **Héberger la démo telle quelle.** Même imparfaite. L'URL existe ce soir.

*Fin de J1 : trois chiffres publiés et une URL vivante.* C'est déjà au-dessus de
la moitié des soumissions.

### J2 — les saisons

5. Multiplicateur de demande : `demande × f_temp(Tmax) × f_événement(jour)`.
   Ouaga va de 32 °C en janvier à **40 °C en avril** : un quart de demande en
   plus sur les mêmes pompes.
6. Calendrier des fêtes : Tabaski (pic de l'année), Ramadan, Noël, 11-Décembre.
7. Réévaluer par saison. **Un tableau à trois lignes — sèche chaude, sèche
   fraîche, pluies — qu'aucun gagnant n'a.**

### J3 — l'alerte

8. `alerte` dans l'action, `confiance` dans l'état, réponse de la population.
9. Réentraîner. Vérifier que la fréquence d'alerte **baisse** pendant que le
   gain monte.
10. Si à 18 h ça ne converge pas : **on coupe l'alerte** et on garde tout le
    reste. C'est le différenciateur, pas le socle.

### J4 — la ville

11. Open-Meteo : géocodage + archive quotidienne. **Sans clé, vérifié le
    10 août** — Ouagadougou et Sydney répondent en une requête.
12. Entraînement par *domain randomisation* sur une distribution de climats.
    Sans ça, le sélecteur est une façade ; avec, c'est une propriété du modèle.
13. Sydney dans la démo : hémisphère sud, saisons inversées, **la
    généralisation se voit en trois secondes.**

### J5 (14 août) — la soumission

14. Write-up 2 000 mots.
15. Vidéo ≤ 3 min, publiée sur YouTube **le 14 au soir**.
16. Formulaire Devpost **soumis le 14**, pas le 15.

---

## Le tableau de coupe

Si le temps manque, on coupe **dans cet ordre**, du bas vers le haut :

| Priorité | Élément | Coupe-t-on ? |
|---|---|---|
| 1 | chiffres vs baselines | jamais |
| 2 | URL hébergée | jamais |
| 3 | unités humaines + CO₂ | jamais |
| 4 | write-up 2 000 mots | jamais |
| 5 | vidéo | jamais |
| 6 | saisons + températures | seulement si J3 dérape |
| 7 | sélecteur de ville | **coupable** |
| 8 | alerte + confiance | **coupable en premier** |

Les cinq premiers font une soumission complète. Les trois derniers font gagner
des catégories supplémentaires. **On ne sacrifie jamais un obligatoire pour un
bonus** — c'est l'erreur qui a coûté Backblaze.

---

## Ce qu'on ne refait pas

- On ne déploie pas en dernier. **L'URL existe le soir de J1.**
- On ne chasse pas de fournisseur. Tout tourne en local, Open-Meteo est sans clé
  et vérifié.
- On n'écrit pas la soumission à la fin. Ce document *est* le brouillon.
- On ne vérifie pas par le texte extrait. On **regarde** la page, la vidéo, le
  formulaire, avec les yeux.
