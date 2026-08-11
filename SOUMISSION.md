# WIIGA — Devpost submission

*Structured on the five headings the hackathon asks for, in their order. Numbers
marked `{{…}}` are filled from `resultats/*.json` in the final pass — nothing in
this document is typed by hand twice.*

---

## Project Title

**WIIGA — a reinforcement-learning operator for city water under load shedding**

*Wiiga* means "the well" in Mooré, the language spoken in Ouagadougou.

---

## Problem Statement

In Ouagadougou, Burkina Faso, the electricity grid is load-shed for roughly
**eight hours a day**, and hardest in the evening — exactly when a residential
district wants water. The utility runs its pumps on a fixed setting written years
ago: full power at night, idle by day, always on the grid.

That setting is not stupid. It is what a careful operator chooses when they have
no tool to do better. But it has three costs, and they are all paid by the same
people:

- **Districts run dry.** Under the current fixed setting, our simulation leaves
  the worst-served district without water {{h_terrain}} hours a day on average.
- **Diesel burns to catch up.** When the tank empties during an outage, the only
  remaining option is the generator — the most expensive and the dirtiest source.
- **The pain is unequal.** Averages hide it. A policy that keeps two districts
  full and drains a third looks excellent on a dashboard and is unacceptable to
  the third district.

The deeper problem is that the decision is genuinely hard. To know whether to
pump *now*, an operator has to hold four things together that do not arrive at
the same time: the district's peak six hours out, the sun's arc, the risk of a
cut this evening, and how much diesel is left in the tank. Nobody does that well
by hand, twenty-four times a day, every day.

---

## Solution Overview

WIIGA is two things, and the second is what makes the first safe.

**A digital twin of the network.** A simulated replica of the physical system —
three district tanks, three pumps, three energy sources, a grid that fails,
demand that follows heat and holidays — calibrated on measured data: three years
of daily ERA5 records for Ouagadougou, and the 2026 Burkinabè holiday calendar.
You do not connect an agent to a city's water supply without one. The twin is
also useful on its own: you can ask it questions about the real network without
touching a valve.

**A PPO agent that operates the twin.** Every hour it sets each pump's power and
picks its energy source, and it can decline — *hand back* an hour to the
operator's fixed setting, which costs a little and is safe. Nobody plugs a black
box into a city's water; an agent that can say "not this hour" is deployable.

Two design decisions separate it from the published literature on pump
scheduling:

**The reward reads the worst-served district, not the average.** `min`, not
`mean`. One line, and it carries the project. With an average, draining one
district to keep two full is a good policy.

**The tank is the battery.** Solar is free at 1 p.m. and gone by 7 p.m., which is
when demand peaks. Storing that energy would mean lithium. But the storage is
already on site — pumping at midday into a district that consumes nothing at
midday is not waste, it is storage. You are not storing electricity, you are
storing work already done.

---

## Key Features

### 1. It decides when to warn the city

The agent has one action that touches no pump: **broadcast a warning to fill
jerrycans before the cut**. This action does not exist in the pump-scheduling
literature, for a reason that is not technical — in Europe nobody stores water at
home. Here every household has containers, and one sentence at 5 p.m. moves more
water than an hour of diesel.

It is not a free button:

- **Warning moves demand forward, it does not remove it.** Households draw now
  what they would have drunk later. The tank is under *more* strain in the
  following hour and less during the cut. Daily volume is conserved exactly.
- **The cost of the action is the future effectiveness of that same action.** A
  false alarm costs no fuel and no money. It costs being listened to.
- **Credibility is lost faster than it is earned.** A correct warning buys
  **+0.04** of trust; a false one costs **−0.15**. That asymmetry alone fixes a
  break-even accuracy of **78.9 %**. No penalty term forbids chatter — it is
  simply a losing bet, and the agent has to work that out.

Measured, with the warning switched off and everything else identical:
{{ablation}}.

### 2. It knows what time of year it is

Ouagadougou does not have one water problem, it has three. April: 39.8 °C,
demand up a quarter, grid failing every evening — but clear skies, so the
tank-as-battery works. August: 30.1 °C and 8.7 mm of rain a day — demand falls,
and so does the sunshine the battery depends on. The two seasons want opposite
policies. Tabaski multiplies a day's demand by 1.6 on tanks that do not grow for
the occasion; Ramadan does not raise demand, it moves the peak to sunset, which
is harder.

### 3. It works in a city it has never seen

Type a city name. Geocoding and three years of daily records arrive in about two
seconds, with no API key and no account, and are cached to disk so the demo runs
offline afterwards. Season boundaries are computed from that city's own
distribution, not from fixed thresholds — a fixed threshold called Sydney "rainy
season" for 365 days a year.

Then the honest test: **the Ouagadougou weights, replayed unchanged on climates
that were not in training**. {{transfert}}

### 4. It says how much infrastructure it replaces

Because the twin is a model of the real network, you can ask it capital
questions. We ask the one a utility director actually asks:

> How much bigger would the tanks have to be for the hand-written rulebook to
> serve the city as well as the agent serves it with the tanks we already have?

{{equivalence}}

### 5. Every number regenerates from a command

No figure in the repository, the demo page or this text was typed twice. Two
scripts produce two JSON files; the README and the web page read them. If a
number is wrong, the measurement is wrong, and it is fixed at the source.

---

## Technologies Used

| | |
|---|---|
| **Reinforcement learning** | Stable-Baselines3 2.7.1 (PPO), Gymnasium 1.2.3 |
| **Numerics** | NumPy |
| **Data** | Open-Meteo geocoding + ERA5 daily archive (keyless), 2023–2025 |
| **Demo** | a single static HTML file with its data written inside it — no server, no serverless function, no network request |
| **Language** | Python 3.13 |

Deliberately absent: no LLM, no cloud API, no GPU. Training takes about twenty
minutes on a laptop CPU, and the whole project runs offline. A utility in
Ouagadougou can run this on the hardware it has.

---

## Target Users

**Directly: the operators of a small urban water utility** in a city with an
unreliable grid — Ouagadougou, Bobo-Dioulasso, and the several hundred cities
across the Sahel and South Asia with the same constraint. The agent produces an
hourly schedule; the *hand back* action means it can be adopted gradually rather
than trusted all at once.

**Through them: the 22,000 people** in the three modelled districts. The unit
that matters is not cubic metres, it is **person-days above the WHO survival
threshold of 20 L**: {{humain}}

**And: whoever plans the network.** The twin answers "how much storage do we need"
before anyone pours concrete.

---

## What this is not

Stated plainly, because a limitation you declare yourself is worth more than one
a judge finds.

- **PPO for pump scheduling is established work**, and so is solar-diesel
  dispatch. What is new here is the objective and the communication action, not
  the algorithm.
- **The hydraulics are a mass balance per tank, not EPANET.** No head loss, no
  pipe network, no pressure. Right for hourly scheduling; wrong for anything
  touching a real valve.
- **The load-shedding model is hand-calibrated**, not fitted to utility outage
  records — those are not published. The agent's advantage is measured against
  rules living under the *same* model, so the comparison stays fair even where
  the model is wrong.
- **Household jerrycan behaviour is a model, not a measurement.** 45 % maximum
  response, six-hour drawdown. The order of magnitude carries the argument; the
  exact figure needs a field survey.
- **Transfer is climatic only.** District profiles, tank sizes and the
  load-shedding regime stay those of Ouagadougou.
- **The demand elasticity to heat — 2.5 % per °C above 30 °C — is the weakest
  assumption in the project.** It sits next to the constant in `calendrier.py`
  rather than buried in it. The literature spans 1–4 % for hot climates.

---

## What did not work

Six mechanisms were built, measured, and thrown away. They are documented in the
code at the exact place they failed, because a project that only reports its
successes is a project you cannot check.

- **Letting the agent repeat itself produced two opposite degenerate optima.**
  Same reward, same environment, two training seeds. One learned to *never speak*
  — zero warnings, trust frozen at its starting value forever. The other
  chattered at seven warnings a day and hit the distrust floor on day 14 *despite
  87 % accuracy*, because almost every warning landed while another was still
  awaiting judgement: those earn nothing, while the 13 % that were wrong cost full
  price. Neither learned to speak rarely and well. The reward structure was
  sound — break-even at 78.9 % — the problem was **exploration**: nothing guided
  the agent between silence and shouting. The fix is what every real alerting
  system does: **the broadcaster does not re-send while the previous warning is
  still live.** One decision remains — *when* to spend a warning — and the result
  is 0.87 warnings a day at 95 % accuracy, with trust climbing to its maximum.
- **Raising the discount factor to see reputation further ahead broke the
  pumping.** Reputation lives on weeks; at γ = 0.98 the agent's useful horizon is
  about two days. Raising it to 0.995 — an eight-day horizon — sounded right and
  measured wrong: all three seeds fell *below* the hand-written rulebook, 0.82 dry
  hours a day against 0.33. **The two sub-problems do not share a natural
  horizon.** Pumping is intraday — the tanks refill every morning, and nothing
  decided today reaches eight days out. Forcing the value function to predict that
  far through a random day-of-year and random outages teaches it nothing and adds
  noise to the advantage estimate on the only part of the problem that yields
  water. What the horizon was meant to buy, the broadcast lock provides
  structurally.

- **Trust clamped at zero made lying free.** Once at the floor, the subtraction
  was clipped, so a false alarm cost nothing while household response was already
  zero — an absorbing state with no cost. The agent fell into it and stayed,
  broadcasting seven times a day at 57 % accuracy. Below zero there is not an
  absence of trust but *active disbelief*: response stays zero, and every further
  lie still digs.
- **The textbook form of potential-based reward shaping charged rent.**
  `γ·Φ(s′) − Φ(s)` costs `(1−γ)·Φ` every step merely for *holding* the potential:
  measured, a day with no warning at all cost −10.6, and a trusted utility paid
  twice what a discredited one paid. It rewarded destroying your own reputation.
- **Two definitions of "repeating yourself" failed.** Comparing to the hour of
  the previous warning leaked across days — a 2 a.m. warning counted as a repeat
  of 3 p.m. the day before. Using jerrycan fill never bit: at starting trust the
  containers never pass half full, so four warnings in a row *gained* trust.
  What works needs no constant: you are repeating yourself when you speak again
  before you have been judged.
- **Ending the episode at midnight told the agent the future was worthless.**
  `terminated=True` at 23:00 zeroes the value of tomorrow. Harmless while only
  tanks existed — they refill every morning — but reputation crosses days, and
  the agent had no reason to protect it. Measured: the floor reached on day 7,
  then 358 days of broadcasting into a city that had stopped listening. Midnight
  is a measurement boundary, not the end of the world.

---

## Repository

`github.com/…` — every module opens with an explanation of *why* it is shaped the
way it is. **The code is documented in French**: WIIGA is built for a francophone
utility in Burkina Faso, and the person who would maintain it reads French.
