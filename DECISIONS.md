# Every choice, what else was possible, and why

A results table shows what a project achieved. It does not show what it decided,
and a project is mostly decisions. This file is the log of ours: what we picked,
what the alternative was, why we picked it, and the one place a reader can check
that the reason is real rather than written afterwards.

Nothing here is new evidence. Every row points at code, a command, or a table
that already exists.

---

## 1. The problem we chose

| Choice | What else was possible | Why | Check |
|---|---|---|---|
| Water pumping **under load shedding** | Pump scheduling under a tariff, which is what most published work does | Almost all RL work on pumping assumes the grid is up and arbitrates peak against off-peak. That is the question of a country where the power stays on. Here the question is filling **before** it leaves | `wiiga/grid.py` |
| **One station**, three districts, 22 000 people | Modelling Ouagadougou as a whole | Ouagadougou's shortfall alone is about 52 times the entire demand we model. A station is the unit an operator actually controls, and the unit that can be adopted one hour at a time | README, *Does this simulator look like the city* |
| A **milder** grid than reality | Matching the 14 h/day measured in April 2024 | Our hot season runs 8.6 h/day. We set the constant that carries the whole problem conservatively, so the advantage is measured under a grid that fails less than the real one did | `python -m wiiga.prevision` |

## 2. The objective

| Choice | What else was possible | Why | Check |
|---|---|---|---|
| Reward reads the **worst-served district** (`min`) | The average, which is what the literature optimises | With an average, draining one district to keep two full is an excellent policy and an unacceptable one | `wiiga/env.py`, `_recompense` |
| Publish the **cost** of that choice | Publishing only the headline | Max-min does not improve every district. Ours is worse than the rulebook on the market district (0.10 against 0.01) and ten times better on the residential one. It flattens the spread; it does not dominate | README, *The same hours, district by district* |
| **Never publish the reward** | Reporting reward curves, as most RL write-ups do | The reward is hand-written, so improving it proves nothing. Every published number is a task metric: dry hours, people below the WHO threshold, francs, CO2 | `python -m wiiga.detournement` |

## 3. The world we simulate

| Choice | What else was possible | Why | Check |
|---|---|---|---|
| Tank as a **mass balance**, not EPANET | A full hydraulic model with head loss and pressure | For an hourly scheduling decision this is the right level of detail. For anything touching a real valve it is not, and we say so | `wiiga/env.py` |
| **Finite diesel**, 320 kWh a day (91 L) | Unlimited generator | Measured: with unlimited diesel a dumb rule that starts the generator never leaves a district dry, and the problem disappears. Swept from 80 to 1280 kWh | `python -m wiiga.sensibilite` |
| Pumps at **2.5x** their own peak hour | One constant power for all three | A first version gave 20 kW to everyone: the city asked 1 100 m3/day and three pumps at full power delivered 792. No policy could serve the city, so no policy could beat another | `wiiga/env.py`, `MARGE_POMPE` |
| Outages are **probable, persistent, and worst in the evening** | A fixed outage schedule | A schedule removes the decision. The agent receives a forecast, never the truth, and the forecast is worst exactly in the season that matters | `wiiga/grid.py` |
| Seasons drive demand **and** the outage regime | Seasons on demand only | Load shedding follows the dam level and the air-conditioning peak, so it follows the season. Without that table the simulator contradicted itself | `wiiga/grid.py`, `REGIME_PAR_SAISON` |

## 4. What the agent is allowed to do

| Choice | What else was possible | Why | Check |
|---|---|---|---|
| An action that **warns the city** | Only pump actions | In this part of the world every household stores water. One sentence at 5 p.m. moves more water than an hour of diesel. In Europe the action would be meaningless | `wiiga/alerte.py` |
| Credibility is a **depletable resource**, +0.04 correct, -0.15 false | A penalty term forbidding chatter | The asymmetry alone fixes a break-even accuracy of 78.9 %. Nothing forbids talking; talking too often is simply a losing bet the agent must work out | `wiiga/alerte.py` |
| Distrust goes **below zero** | Clamping trust at zero | Measured: clamped at zero, lying became free once at the floor, and the agent sat there broadcasting seven times a day at 57 % accuracy. Below zero there is not an absence of trust but active disbelief | README, *What did not work* |
| The broadcaster **does not repeat** while a warning is pending | Letting the agent re-send | Measured: without it, two seeds on the same reward found opposite degenerate optima - one never spoke, the other shouted seven times a day and lost all credibility by day 14 despite 87 % accuracy | `wiiga/env.py` |
| The agent may **hand the hour back** | Full autonomy | Nobody connects a black box to a city's water. An agent that can say *not this hour* is adoptable gradually. It pays 3.0 of reward to do it, and it does it at 3, 6 and 7 a.m. | the live demo, hour slider |

## 5. How it learns

| Choice | What else was possible | Why | Check |
|---|---|---|---|
| **PPO on Stable-Baselines3 defaults** | Tuning until the numbers improve | Six variants trained and measured - longer, wider, entropy bonus, normalised reward, decaying learning rate, bigger batch. **All six are worse**, and inter-seed noise is 0.06 h | `python -m wiiga.reglages` |
| Discount **0.98**, not 0.995 | A longer horizon so reputation is visible | Measured: at 0.995 all three seeds fell below the hand-written rulebook. Pumping is intraday and tanks refill each morning; the two sub-problems do not share a horizon | README, *What did not work* |
| Midnight is **truncation**, not termination | Ending the episode at midnight | Terminating tells the agent the future is worthless. Harmless while only tanks existed; reputation crosses days, and the agent fell to the distrust floor by day 7 | `wiiga/env.py` |
| Trust **randomised in training, persistent in evaluation** | The same setting for both | In training the agent must meet the whole range of credibility or it destroys the channel in its first twenty days. In evaluation trust carries over, because that is deployment | `wiiga/train.py` |
| **CPU, 8 parallel environments** | A GPU | The policy is two layers of 64. What costs time is the Python environment loop, and a GPU does not accelerate a Python loop. Cores do | `wiiga/train.py` |

## 6. How we measure

| Choice | What else was possible | Why | Check |
|---|---|---|---|
| **Three seeds**, and the worst one is the number to plan with | One training run | PPO is stochastic and a single lucky run proves nothing. All three beat the rulebook; the spread is published | `resultats/graines.json` |
| **One published model**, named once | Each command choosing its own | The commands used to load two different models, so a reader running the documented command got numbers close to the tables and not equal to them | `MODELE_PUBLIE` in `wiiga/train.py` |
| Tune the **opponent** against ourselves | Comparing to the rule as first written | The rulebook's two constants were swept over a 6x5 grid. Ours was under-tuned by 13 %, and the agent still beats the best of the family | `python -m wiiga.meilleure_regle` |
| Add the method a **control engineer** would pose | Stopping at hand-written rules | Every other opponent is written by us. A receding-horizon MPC is not a rule, it is the standard formulation. The agent serves 82 % better; the controller runs the station for 48 % less | `python -m wiiga.mpc` |
| Break our **own weakest assumption** | Declaring it and moving on | Demand elasticity was the shakiest thing in the project, so one district was made to drink 30 % more than the forecast said, unannounced. The conclusion does not move | `python -m wiiga.choc` |
| Publish the **failures** | Publishing successes only | Nine mechanisms were built, measured and thrown away, each documented at the line where it failed - including a CVaR variant that collapsed to 48.2 dry hours a day | README, *What did not work* |
| **19 property tests**, no dependencies | Trusting the code | They check the five properties the argument rests on, not the implementation. A test that mirrors the code proves only its own existence | `python -m wiiga.tests` |

## 7. How we deliver it

| Choice | What else was possible | Why | Check |
|---|---|---|---|
| **One static file, zero network requests** | A small server or a serverless function | A deployment detail cost us a previous competition. This page cannot break in front of a judge because an API changed its mind. Data is written inside the HTML at build time | `demo/construire.py` |
| Every table **regenerated** from JSON | Typing numbers into the README | A number typed by hand survives the measurement that produced it, and you end up defending in public a result that no longer exists in the code. Narrative prose does copy figures, and says so | `python -m wiiga.rapport` |
| Code in **French**, entry files summarised in English | English throughout | WIIGA is built for a francophone utility, and whoever maintains it reads French. But the language must not be a toll at the door: `env.py`, `alerte.py` and `resultats.py` open in English | any file in `wiiga/` |
| **No video** | A narrated walkthrough | Not required by the rules, and the live console does the job in twenty seconds without an accent between the judge and the argument | the demo |
| A tool that answers about **your** station | A demo that replays ours only | Three sweeps already measured were made turnable, so an operator reads what the agent buys at their diesel budget, their pumps, their forecast error - one axis at a time, because the combinations were never measured | the demo, *Your station, not ours* |

---

## What we did not decide, and would decide with a week more

- **Talk to an operator.** Twenty minutes on the phone with someone who runs a
  station would replace three paragraphs of assumption with fact. It is the
  single most valuable thing that could happen to this project, and it has not
  happened.
- **Hold out a slice of the year.** The agent trains on days drawn from the same
  calendar the evaluation replays; only the outage draws differ. A proper
  temporal split would answer a reflex every ML reviewer has.
- **A stochastic MPC.** Ours plans against the expectation of grid availability.
  A scenario-based controller would be a fairer opponent still, and it is a
  different piece of work.
