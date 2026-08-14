# What we searched, what we found, and what we now claim

The submission says the communication action has no equivalent in the
pump-scheduling literature. Until now that was an assertion. This file is the
search behind it, and it changed the claim - for the better, because it names
the closest antecedent instead of waiting for a judge to name it.

## What already exists, and is close

**Reputational cheap talk (economics).** In reputational cheap-talk games an
expert's advice is a *reputation-dependent cutoff on their own signal*, and the
literature reports **reputational conservatism**: the cutoff rises with
reputation, so a more trusted expert speaks more selectively. This is the
closest antecedent we found to WIIGA's warning channel, and the resemblance is
real - our agent also sets a threshold on its outage forecast, and its
credibility is a state that its own past accuracy moved.

Two differences remain. In those models reputation is a **belief held by a
Bayesian audience about the expert's type**; here it is an **explicit scalar the
environment carries**, with a stated update rule (+0.04 correct, -0.15 false)
whose asymmetry alone fixes a break-even accuracy of 78.9 %. And there the
expert is an advisor with no other action; here speech sits **inside a control
problem**, competing for the same objective as three pumps, a diesel budget and
a failing grid.

**Cheap talk in multi-agent RL.** Work exists on discovering and using cheap-talk
channels between learning agents. The framing is explicit that these are **free
communication channels** - messages cost nothing and the question is whether
agents learn to use them informatively. WIIGA's channel is the opposite case:
the message is free in fuel and money, and **costly in future channel capacity**.

**RL for demand response.** Reviews exist, and it is an established field. But
published demand response shifts **industrial or appliance load through
pricing**, and where consumer trust appears it is an **interpretability and
fairness concern** for the designer - not a state variable the agent spends and
must husband.

## What we did not find

A single-agent control problem in which communication to **humans** is one action
among physical ones, and its effect is scaled by an **endogenous credibility
state that depletes asymmetrically and is part of the observation**.

We did not find it. We are not claiming it does not exist - one search is not a
systematic review, and we say so. What we claim is narrower and checkable:
**this combination is not standard in the pump-scheduling or demand-response
literature we searched, and the closest antecedent we found is reputational
cheap talk, which we name here rather than leave for someone else to find.**

## Sources

- Cheap Talk Discovery and Utilization in Multi-Agent Reinforcement Learning - https://arxiv.org/abs/2303.10733
- Cheap Talk, Reinforcement Learning, and the Emergence of Cooperation - https://www.cambridge.org/core/journals/philosophy-of-science/article/abs/cheap-talk-reinforcement-learning-and-the-emergence-of-cooperation/3E4243FEDA32926DE0D280FC9F9C26CB
- Reputational Cheap Talk - https://www.researchgate.net/publication/24049339_Reputational_Cheap_Talk
- Meaning and credibility in experimental cheap-talk games - https://onlinelibrary.wiley.com/doi/full/10.3982/qe683
- Reinforcement learning for demand response: a review of algorithms and modeling techniques - https://www.sciencedirect.com/science/article/abs/pii/S0306261918317082
- Decentralized multi-agent federated and RL for smart water management - https://www.sciencedirect.com/science/article/pii/S1110016825005186
