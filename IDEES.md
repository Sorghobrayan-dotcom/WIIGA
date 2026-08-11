# WIIGA — chercher loin

Brainstorming. Rien ici n'est décidé, et certaines idées sont volontairement
trop grandes : on coupe après, pas avant.

L'état actuel : un agent PPO qui pilote trois pompes sous délestage, avec une
réserve de gasoil finie, le droit de passer la main, et une récompense qui
regarde le quartier le plus mal servi. C'est déjà au-dessus de la littérature
sur un point — le réseau tombe. Ce qui suit cherche à en être très loin.

---

## Le renversement principal

Aujourd'hui WIIGA **optimise du pompage**. Trois autres façons de poser la même
question, par ordre d'ambition :

### A. WIIGA achète du temps

L'unité de mesure n'est plus le FCFA ni le niveau de cuve. C'est
**l'heure-personne d'accès à l'eau**.

Un mètre cube dans une cuve n'est pas un résultat. Le résultat, c'est qu'une
famille de Tanghin ait eu de l'eau au robinet entre 6 h et 8 h, quand quelqu'un
était là pour la prendre. L'OMS fixe 20 L/personne/jour en survie et 50 L en
besoin de base — l'agent optimise **combien de personnes ont atteint ce seuil**,
et rien d'autre.

Ce que ça change immédiatement :

- l'eau à 3 h du matin ne vaut pas l'eau à 7 h. Elle est pompée mais personne ne
  la prend. Une pondération horaire de l'utilité change complètement la politique
- deux quartiers de tailles différentes ne pèsent plus pareil : 10 000 habitants
  desservis valent plus que 2 000, ce que le niveau de cuve ignore
- le jury lit un nombre humain, pas un nombre d'ingénieur

**Coût : faible.** C'est une réécriture de la récompense et du rapport.
**Valeur : très élevée.** C'est la différence entre un projet d'automatique et
un projet qui sait ce qu'il sert.

### B. L'agent parle aux gens avant de parler aux pompes

C'est l'idée que je crois la plus forte, et elle n'existe nulle part dans la
littérature sur le pompage — pour une raison simple : **en Europe personne ne
stocke l'eau chez soi**. Ici tout le monde a des bidons.

Donc l'agent gagne une action qui n'est pas hydraulique :

> **prévenir.** « Coupure probable ce soir à 19 h. Remplissez vos bidons avant
> 17 h. » Par SMS, par radio de quartier, par WhatsApp.

Les conséquences sont énormes et toutes intéressantes :

- l'agent ne subit plus la demande, il la **déplace**. C'est de la gestion de la
  demande, et c'est infiniment moins cher que du gasoil
- prévenir a un coût réel : la crédibilité. Si l'agent alerte tous les jours,
  plus personne n'écoute. Il doit apprendre **la parcimonie** — n'alerter que
  quand ça compte. C'est un problème d'apprentissage magnifique et non trivial
- un modèle de réponse : une fraction seulement des gens réagit, et cette
  fraction dépend de la confiance accumulée. La confiance se construit lentement
  et se perd d'un coup, comme dans la vraie vie

**Coût : moyen.** Une dimension d'action, un modèle de réponse, un compteur de
crédibilité.
**Valeur : maximale.** C'est le seul élément de cette liste dont je peux dire
qu'aucun jury n'aura vu l'équivalent.

### C. L'agent ne commande rien : il propose, et il apprend d'être refusé

Aucune régie africaine ne branchera un réseau de neurones sur ses vannes. Donc
inverser : WIIGA produit une **consigne recommandée** que l'exploitant approuve,
modifie ou rejette — et **apprend de ce qui est accepté**.

C'est de l'apprentissage par préférences, pas par récompense simulée. Ça résout
d'un coup le problème du déploiement, et ça transforme la faiblesse (« votre
simulateur n'est pas la réalité ») en mécanique du produit.

**Coût : moyen.** Il faut une boucle d'approbation et un modèle de préférence.
**Valeur : élevée**, surtout sur « Real-World Impact ».

---

## Ce que le modèle ignore et qui existe vraiment

### 1. L'eau qui n'arrive jamais

Dans une régie ouest-africaine, **30 à 50 % de l'eau pompée est perdue** —
fuites, branchements illicites, compteurs morts. C'est le premier poste de
gâchis, très loin devant le tarif de pointe.

Un agent qui pompe plus fort dans un quartier qui fuit aggrave le problème. Un
agent qui **détecte la fuite** à l'écart entre volume pompé et volume consommé,
et qui signale « la zone 2 perd 40 %, envoyez une équipe » vaut plus que
n'importe quelle optimisation tarifaire.

C'est aussi un second objectif d'apprentissage : détecter une anomalie sans
qu'on lui ait montré d'anomalies.

### 2. La file d'attente à la borne-fontaine

Le niveau de cuve est une abstraction d'ingénieur. Ce que vit la personne, c'est
**le temps passé debout à la fontaine**. Modéliser la file — arrivées, débit,
attente moyenne — et optimiser l'attente plutôt que le niveau. Et l'attente est
portée à 90 % par des femmes et des enfants, ce qui est une phrase que le jury
n'oubliera pas.

### 3. Le camion-citerne

Quand tout tombe, l'eau arrive par camion. C'est cher, c'est lent, et c'est
réel. L'agent gagne un troisième mode : **planifier une rotation de camions**,
avec un délai de plusieurs heures entre la décision et l'arrivée. Un agent qui
doit décider trois heures à l'avance sur une prévision incertaine — c'est un
problème beaucoup plus riche que d'allumer une pompe.

### 4. La chaleur

Il fait 42 °C en avril, la consommation explose, et le rendement des panneaux
solaires **baisse** quand ils chauffent. Deux effets opposés le même jour.

Tu as déjà une clé OpenWeather dans YILGA. Brancher la météo réelle relie tes
deux projets et remplace une sinusoïde par une donnée.

### 5. Les annonces de la SONABEL

Le délestage est en partie **publié**. Ingérer les annonces réelles, mesurer à
quel point elles sont tenues, et apprendre l'écart entre l'annonce et la réalité
— c'est un jeu de données que personne d'autre n'a et que tu peux constituer.

### 6. Les habitants savent avant la régie

Quelqu'un dont le courant vient de sauter le sait avant le centre de conduite.
Un signalement par SMS ou WhatsApp, agrégé sur un quartier, donne une carte des
coupures **en temps réel**. L'agent apprend de ses utilisateurs.

---

## Rendre l'agent lisible

### 7. Il explique, en une phrase

À chaque heure : « J'ai rempli à fond sur le réseau à 16 h parce que le risque
de coupure à 19 h était de 0,7 et qu'il ne me restait que 30 kWh de gasoil. »

Cher en rien, et ça transforme la perception d'un jury.

### 8. Le contrefactuel

« Si je n'avais pas rempli à 16 h, la zone 2 aurait été à sec à 20 h. » On
rejoue la journée sans la décision et on montre l'écart. C'est ce qui prouve que
l'agent a fait quelque chose, plutôt que d'avoir eu de la chance.

### 9. En mooré et en dioula

L'interface de l'exploitant en français ; les alertes aux habitants **dans la
langue qu'ils parlent**. Ce n'est pas un détail cosmétique : une alerte qu'on ne
comprend pas n'est pas une alerte.

---

## Les idées trop grandes, gardées quand même

### 10. Chaque quartier a son agent, et ils négocient

Multi-agents. Chaque zone défend ses habitants, et un mécanisme d'enchères
répartit l'eau — sous une contrainte d'équité qui interdit à un quartier riche
d'acheter la sécheresse d'un autre. C'est un sujet de recherche entier.

### 11. Le jour où le réseau meurt

Ne plus optimiser : **planifier la résilience**. Quelle est la pire journée
survivable ? L'agent cherche la politique qui maximise le nombre de jours tenus
si le réseau tombe totalement demain. Optimisation du pire cas, pas de la
moyenne — c'est cohérent avec le choix `min` déjà fait sur les quartiers.

### 12. WIIGA au-delà de l'eau

L'objet réel n'est pas l'eau. C'est **piloter un service essentiel sous une
infrastructure qui n'est pas fiable**. Le même agent vaut pour une chaîne du
froid de vaccins, un réseau de recharge de motos électriques, une batterie de
santé rurale. Le dire, une phrase, dans le README.

---

## Ce que je ferais, si je devais choisir trois choses

1. **A — l'heure-personne d'accès à l'eau** comme unité unique. Faible coût,
   change tout le récit, et donne au jury un chiffre humain.
2. **B — l'action « prévenir »** avec un capital de crédibilité qui s'use. C'est
   la seule idée de cette page dont je sois sûr qu'elle est neuve.
3. **7 + 8 — l'explication et le contrefactuel.** Peu de travail, et c'est ce
   qui fait la différence entre « un agent a tourné » et « voici ce qu'il a
   compris ».

Les fuites (1) en quatrième, si le temps le permet : c'est la contrainte la plus
réelle de toutes et elle est chiffrable.
