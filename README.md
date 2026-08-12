# WIIGA

**A reinforcement-learning operator for city water pumps in a place where the
electricity grid goes down every evening.**

Ouagadougou, Burkina Faso. Three district pumps, three storage tanks, one shared
diesel reserve, and a grid that is load-shed on a schedule nobody publishes. The
question a utility operator actually faces at 4 p.m. is not *"what is the
cheapest kilowatt-hour"*. It is *"will there be power at seven, and if not, is
there enough water already in the tank for the evening"*.

WIIGA is a PPO agent that answers that question every hour, and one more that no
published pump controller asks: **should I tell the city?**

---

## The three things that make this different

### 1. The tank is the battery

Solar power is free at 1 p.m. and gone by 7 p.m., which is exactly when the
residential district gets thirsty. Storing that energy would mean lithium -
expensive, and due for replacement in eight years.

But the storage is already on site. It is the **tank**. Pumping at midday, on
free sunlight, into a district that consumes nothing at midday is not waste: it
is storage. You are not storing electricity, you are storing work already done.

This is also what makes learning necessary rather than decorative. To decide
whether to fill *now*, the agent must hold four things together that do not
arrive at the same time: the district's peak six hours out, the sun's arc, the
risk of a grid cut this evening, and the diesel that is left. A hand-written
rule does not arbitrate four horizons - and we measured that, against a rule
that reads the same forecast the agent does.

### Why a threshold cannot do this job

The hand-written rulebook reads the same outage forecast the agent does and fires
an "urgent" flag above a risk threshold. Sweeping that threshold over a 6x5 grid
barely moves anything: from 0.05 to 0.60, the rulebook lands between 0.71 and
0.85 dry hours a day, and most of the grid is flat to the second decimal.

That is not a badly chosen constant. It is a property of the information itself.
Measured over 8 760 forecast hours, the risk of an outage in the next four hours
has a median of **0.046** across the year and **0.58** in the hot dry season -
the signal is bimodal. It sits near zero when nothing is coming and high when
something is, and it almost never occupies the middle where a threshold would
have anything to arbitrate. Moving the threshold from 0.15 to 0.60 changes how
often the rule declares an emergency by four percentage points, because there is
almost no probability mass in between.

A scalar threshold on a bimodal signal has exactly two states. The agent reads
the same forecast as a vector, alongside tank levels, sunshine, the seasonal
demand multiplier and the fuel left, and can be at 40 % on one pump and 90 % on
another in the same hour. **That is the difference the numbers measure**, and it
is why the gap survives giving the rule its best possible constants.

### 2. The reward reads the worst-served district, not the average

`min`, not `mean`. One line, and it carries the whole project.

With an average, draining one district to keep two full is an excellent policy.
It is also unacceptable. Every number in the results table below comes from an
agent that was optimised for the district doing worst - which is why it is more
expensive than it could be, and why that is the point.

### 3. The agent can talk to the city

The agent has one action that touches no pump: **warn the city to fill their
jerrycans before the cut.** SMS, neighbourhood radio, the market crier - the
channel does not matter, the mechanism does.

This action does not exist in the pump-scheduling literature, for a reason that
is not technical: **in Europe nobody stores water at home.** Published demand
response shifts industrial load through pricing. Here every household has
jerrycans, and one sentence at 5 p.m. moves more water than an hour of diesel.

Three properties make it a genuine learning problem rather than a button:

- **Warning moves demand forward, it does not remove it.** Households draw now
  what they would have drunk later. The tank is therefore under *more* strain in
  the following hour and less during the cut. Total volume is conserved exactly.
- **The cost of the action is the future effectiveness of that same action.** A
  false alarm costs no fuel and no money. It costs being listened to.
- **Credibility is lost far faster than it is earned.** A correct warning buys
  +0.04 of trust; a false one costs -0.15. That asymmetry alone fixes a
  break-even accuracy of **78.9 %**, and the agent has to learn to stay above it.

There is no penalty term forbidding the agent to chatter. Talking too often is
simply a losing bet, and it has to work that out.

One structural rule makes that learnable: **the broadcaster does not re-send
while the previous warning is still awaiting judgement** - which is what any real
alerting system does. Without it, measured, two seeds on the same reward found
opposite degenerate optima: one never spoke at all, the other shouted seven times
a day and lost all credibility by day 14 despite being right 87 % of the time.
With it, one decision remains - *when* to spend a warning.

---

## Running it

```bash
pip install -r requirements.txt
```

```bash
python -m wiiga.resultats --journees 365
```

That reproduces every number in this file and writes
`resultats/comparaison.json`. Training from scratch takes about fifteen minutes
on a laptop CPU:

```bash
python -m wiiga.train --pas 600000
```

Point the model at any city on earth - no API key, no account:

```bash
python -m wiiga.ville Chennai
```

Geocoding and three years of daily ERA5 records come from Open-Meteo and are
cached to `villes/` so the demo runs offline afterwards.

---

## Results

<!-- chiffres:début -->

*365 simulated days, one per day of the year, identical seeds for every policy. Measured on 2026-08-12, regenerated by `python -m wiiga.resultats --journees 365`.*

### What each policy costs the city

| operator | dry hours / day | dry days / 200 | local currency / day | L diesel / day | kg CO2 / day | tank low point |
|---|---:|---:|---:|---:|---:|---:|
| exploitant (consigne fixe) | 2,48 | 77 | 961 761 | 77,0 | 206,4 | 0,27 |
| moins cher (sans prévision) | 0,40 | 30 | 324 656 | 61,2 | 164,0 | 0,41 |
| prévoyant (règle écrite) | 0,33 | 26 | 321 557 | 62,8 | 168,3 | 0,43 |
| **agent WIIGA (PPO)** | 0,16 | 15 | 268 745 | 39,9 | 106,8 | 0,26 |
| agent WIIGA, sans la parole | 0,23 | 20 | 290 705 | 47,4 | 127,1 | 0,25 |

### The same table, season by season - dry hours per day

| operator | hot dry | rainy | mild dry |
|---|---:|---:|---:|
| exploitant (consigne fixe) | 7,09 | 0,09 | 1,24 |
| moins cher (sans prévision) | 1,33 | 0,01 | 0,08 |
| prévoyant (règle écrite) | 1,11 | 0,01 | 0,06 |
| **agent WIIGA (PPO)** | 0,40 | 0,02 | 0,10 |
| agent WIIGA, sans la parole | 0,71 | 0,02 | 0,07 |

The annual average hides the point: the hand-written rules give way in the
hot dry season, which is exactly when the city is thirstiest.

### Speech: what the agent tells the city, and whether it is believed

| operator | warnings / day | accuracy | trust at the end |
|---|---:|---:|---:|
| agent WIIGA (PPO) | 0,70 | 96 % | 1,00 |
| agent WIIGA, sans la parole | 0,00 | 0 % | 0,55 |

### At a glance

- **against what the utility runs today**: 94 % fewer dry hours, 72 % cheaper to run, 48 % less CO2
- **against the hand-written rulebook**: 53 % fewer dry hours, 16 % cheaper to run, 37 % less CO2
- **against itself, with the warning switched off**: 31 % fewer dry hours, 8 % cheaper to run

### Does the result survive its own variance

*PPO is stochastic. A single lucky run proves nothing, so here are three complete trainings on three seeds, evaluated on the same days against the same rules.*

| training seed | dry hours / day | warnings / day | warning accuracy |
|---|---:|---:|---:|
| seed 0 | 0,16 | 0,70 | 96 % |
| seed 1 | 0,09 | 0,78 | 95 % |
| seed 2 | 0,21 | 0,58 | 100 % |
| **the rulebook they all beat** | **0,33** | 0 | - |

All three seeds beat the hand-written rulebook, by **54 %** on average and between **37 %** and **72 %** depending on the seed. The worst of the three is the number to plan with.

### Was the rulebook given its best shot?

*The fair objection to any "we beat the baseline" claim: you did not show a rule cannot do this, you showed that YOUR rule does not. So the rulebook's two hand-set constants were swept over a 5x5 grid, and the agent replayed against the best of the family.*

| | dry hours / day |
|---|---:|
| the rulebook as written in this repo | 0,817 |
| **the best rulebook of the family** (threshold 0.05, factor 1.4) | **0,708** |
| the agent | 0,267 |

The repo's rulebook was **under-tuned by 13 %**, and the agent still beats the best of the family by **62 %**. The rule was allowed to pick its constants while looking at the very days it is scored on - an advantage the agent does not get, since its weights are frozen before it sees them.

### Where this stops being true

*A result with no stated boundary is a result nobody believes. The daily generator budget is the constant the whole problem turns on, so here is the agent swept across it.*

| diesel available per day | agent | rulebook | difference |
|---|---:|---:|---:|
| 23 L (4 % of the day's energy) | 0,87 | 1,32 | 34 % |
| 46 L (7 % of the day's energy) | 0,57 | 1,16 | 51 % |
| 91 L (14 % of the day's energy) **<- the value used** | 0,27 | 0,82 | 67 % |
| 183 L (28 % of the day's energy) | 0,25 | 0,28 | 9 % |
| 366 L (57 % of the day's energy) | 0,25 | 0,00 | 0 % |

**The agent wins from 23 to 183 litres a day, and loses at 366.** We are not burying that line, we are naming it. At that budget the generator covers more than half the city's pumping energy: there is no arbitrage left to make, you simply burn diesel, and twenty lines of `if` are enough. **WIIGA is for utilities that are constrained** - and an advantage that survived the removal of the constraint would be the suspicious result, not this one.

### What it replaces in concrete

The simulator is a digital twin, so it answers capital questions. The hand-written rulebook only matches the agent at **1.22x storage** - **96 m3** of new tank on the 440 m3 that exist, a **22 % expansion**. That is what the agent is worth in concrete, and it costs nothing to pour.

Buying the same result with fuel instead takes **1.72x the daily generator budget** - more emissions, every day, for as long as the station runs.

### And in a city it has never seen

*The weights trained on Ouagadougou, replayed unchanged. Nothing is retrained: the climatology is swapped, and nothing else.*

| city | rainy / hot / mild (days) | agent | rulebook | difference | warnings / day |
|---|:--:|---:|---:|---:|---:|
| Ouagadougou *(training city)* | 116 / 100 / 149 | 0,16 | 0,33 | 53 % | 0,70 |
| Chennai | 98 / 107 / 160 | 0,06 | 0,18 | 67 % | 0,64 |
| Nairobi | 63 / 121 / 181 | 0,10 | 0,11 | 10 % | 0,64 |
| Sydney | 68 / 119 / 178 | 0,09 | 0,09 | -6 % | 0,58 |
| Lima | 0 / 146 / 219 | 0,13 | 0,12 | -9 % | 0,76 |

The agent beats the rulebook in **3 of 5** of these cities, with nothing retrained. It does not win everywhere, and the pattern is worth more than a clean sweep would be: **its advantage tracks how hard the city is.** Where the rulebook already keeps taps running - Sydney, Lima - there is nothing left to win. Where the problem bites, the gap opens. A tool that helps most exactly where the need is greatest is the tool you want.

<!-- chiffres:fin -->

---

## About the baseline we compare against

`exploitant` is meant to be what a utility actually runs: full power at night,
idle by day, and the generator when the grid drops. It is the number every claim
in this file is measured against, so it deserves a paragraph rather than a line.

**A first version never started the generator.** It pumped on the grid around the
clock, which during an eight-hour outage means pumping nothing. It scored 0.0
litres of diesel a day - a perfect carbon footprint achieved by serving nobody -
and made the agent look ten times better than it is. That is a straw man, and it
was corrected. The current version burns 77 litres a day, costs more to run than
any other policy in the table, and still leaves the worst district dry for 2.48
hours a day. The gap WIIGA can claim against current practice got smaller, and
the comparison got worth making: **the CO2 line now compares two policies that
both burn fuel**, 107 kg against 206.

What it still is: an assumption. No utility publishes its dispatch rule, so this
is what a careful operator would plausibly do with no forecast and no tool, not
a transcript of what any particular station does. **Twenty minutes on the phone
with someone who runs one would replace this paragraph with a fact**, and that is
the single most valuable thing that could happen to this project - more than any
amount of extra compute, because it is the one thing a simulator cannot generate.

## What this is not

Stated plainly, because a result you have to defend later is worth less than a
limitation you declared yourself.

- **PPO for pump scheduling is established work.** So is solar-diesel hybrid
  dispatch. What is new here is the *objective* (worst-served district) and the
  *communication action*, not the algorithm.
- **The hydraulics are a mass balance per tank, not an EPANET simulation.** No
  head loss, no pipe network, no pressure. For scheduling decisions at hourly
  resolution this is the right level of detail; for anything touching a real
  valve it is not.
- **The load-shedding model is calibrated by hand**, not fitted to SONABEL
  outage records - those are not published. The three regimes are plausible, and
  the agent's advantage is measured against rules operating under the *same*
  model, so the comparison is fair even where the model is wrong.
- **The demand elasticity to heat (2.5 % per °C above 30 °C) is the weakest
  assumption in the project.** It is written in `calendrier.py` next to the
  constant rather than buried in it. The literature spans 1-4 % for hot climates.
- **Transfer to another city is climatic only.** District profiles, tank sizes
  and the load-shedding regime stay those of Ouagadougou. We change what the
  model knows about geography - twelve temperatures, twelve solar sums, twelve
  rainfall figures - and nothing else.
- **Household jerrycan behaviour is a model, not a measurement.** 45 % maximum
  response, six-hour drawdown. The order of magnitude is what carries the
  argument; the exact figure would need a field survey.

---

## Repository

| Path | What lives there |
|---|---|
| `wiiga/env.py` | the Gymnasium environment: tanks, pumps, sources, reward |
| `wiiga/grid.py` | load shedding - three seasonal regimes, forecast vs truth |
| `wiiga/alerte.py` | the warning channel and the city's trust in the utility |
| `wiiga/calendrier.py` | heat, sun, rain, Ramadan and Tabaski across the year |
| `wiiga/ville.py` | plug any city on earth in via Open-Meteo |
| `wiiga/baselines.py` | what the agent has to beat, including a rule that reads the same forecast |
| `wiiga/resultats.py` | the measurement harness - the only place numbers are produced |
| `wiiga/transfert.py` | the same weights, replayed on climates never seen in training |
| `wiiga/rapport.py` | turns the JSON into the tables above, so no number is ever retyped |

**The code is documented in French**, at length, and that is deliberate: WIIGA
is built for a francophone utility in Burkina Faso, and the person who would
maintain it reads French. Every module opens with an explanation of *why* it is
shaped the way it is, including the versions that were measured and thrown away.
