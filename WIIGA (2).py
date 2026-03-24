import gymnasium as gym
from gymnasium import spaces
import numpy as np
import wntr
import matplotlib.pyplot as plt
from stable_baselines3 import PPO
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

# ---------------------------------------------------------
# Définition de l'environnement WIIGA
# ---------------------------------------------------------
class WIIGAEnv(gym.Env):
    def __init__(self, inp_file, n_pumps=3, n_tanks=3, max_steps=24):
        super(WIIGAEnv, self).__init__()

        # Charger le réseau EPANET ou créer un réseau synthétique
        try:
            self.wn = wntr.network.WaterNetworkModel(inp_file)
        except:
            self.wn = wntr.network.WaterNetworkModel()
            for i in range(n_tanks):
                self.wn.add_tank(f'Tank{i+1}', elevation=10, init_level=5, min_level=0, max_level=20)
            for i in range(n_pumps):
                self.wn.add_pump(f'Pump{i+1}', 'Source', f'Tank{(i % n_tanks) + 1}', info={'power': 15})

        self.pumps = self.wn.pump_name_list
        self.tanks = self.wn.tank_name_list
        self.n_pumps = len(self.pumps)
        self.n_tanks = len(self.tanks)
        self.max_steps = max_steps

        # Définition de l'espace d'action et d'observation
        self.action_space = spaces.Box(low=0, high=1, shape=(self.n_pumps * 2,), dtype=np.float32)
        self.observation_space = spaces.Box(low=0, high=1, shape=(self.n_tanks + 3,), dtype=np.float32)
    def _get_solar_availability(self, hour):
        if 7 <= hour <= 17:
            return np.sin(np.pi * (hour - 7)/10)
        return 0.0

    def _get_demand_forecast(self, hour):
        demand = 0.3 + 0.5 * np.exp(-(hour - 7)**2 / 4) + 0.6 * np.exp(-(hour - 19)**2 / 4)
        return np.clip(demand, 0, 1)

    # Obtenir l'état actuel
    def get_state(self):
        levels = [self.wn.get_node(t).level / self.wn.get_node(t).max_level if hasattr(self.wn.get_node(t),'level') else 0.5 for t in self.tanks]
        hour_norm = self.current_step / self.max_steps
        demand = self._get_demand_forecast(self.current_step)
        solar = self._get_solar_availability(self.current_step)
        return np.array(levels + [hour_norm, demand, solar], dtype=np.float32)

    # Réinitialiser l'environnement
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        for t in self.tanks:
            self.wn.get_node(t).level = 5.0
        return self.get_state(), {}

    # Exécuter un pas de simulation
    def step(self, action):
        hour = self.current_step
        reward = 0
        pump_power = action[0::2]
        source_idx = (action[1::2]*2.99).astype(int)

        solar_ok = self._get_solar_availability(hour)
        is_peak_grid = 18 <= hour <= 22
        total_cost = 0

        for i, pump in enumerate(self.pumps):
            power = pump_power[i]
            src = source_idx[i]
            energy_used = power * 20

            # Calcul des coûts et récompenses
            if src == 0: # solaire
                if solar_ok > 0.2:
                    reward += 0.5 * power
                else:
                    total_cost += energy_used * 500
                    reward -= 10
            elif src == 1: # réseau
                price = 250 if is_peak_grid else 120
                total_cost += energy_used * price
                if is_peak_grid:
                    reward -= 2
            else: # groupe diesel
                total_cost += energy_used * 400
                reward -= 5

            # Mise à jour niveau des cuves
            tank = self.wn.get_node(self.tanks[i % self.n_tanks])
            demand_volume = self._get_demand_forecast(hour)*50
            pumped_volume = power * 80
            tank.level += (pumped_volume - demand_volume)/100
            tank.level = np.clip(tank.level, 0, tank.max_level)

            # Pénalités de sécurité
            if tank.level < 2.0: reward -= 50
            elif tank.level > 18.0: reward -= 10

        # Pénaliser coût global
        reward -= total_cost/1000

        self.current_step += 1
        done = self.current_step >= self.max_steps
        return self.get_state(), reward, done, False, {}

    # Affichage simple
    def render(self, mode='human'):
        print(f"Step {self.current_step}, Tanks: {[self.wn.get_node(t).level for t in self.tanks]}")

# ---------------------------------------------------------
# Entraînement de l'agent PPO
# ---------------------------------------------------------
def train_wiiga(total_timesteps=50000):
    env = WIIGAEnv("reseau_onea.inp")
    model = PPO("MlpPolicy", env, verbose=1, learning_rate=0.0003, tensorboard_log="./logs/")
    model.learn(total_timesteps=total_timesteps)
    model.save("wiiga_final_model")
    print("Modèle WIIGA entraîné et sauvegardé.")
    return model

# ---------------------------------------------------------
# Simulation et visualisation
# ---------------------------------------------------------
def run_demo(model_path="wiiga_final_model"):
    env = WIIGAEnv("reseau_onea.inp")
    model = PPO.load(model_path)
    obs, _ = env.reset()
    history = {'levels':[[] for _ in env.tanks], 'sources':[[] for _ in env.pumps], 'rewards':[]}

    for h in range(env.max_steps):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)
        history['rewards'].append(reward)
        for i, t in enumerate(env.tanks):
            history['levels'][i].append(env.wn.get_node(t).level)
        for i, p in enumerate(env.pumps):
            history['sources'][i].append(["SOLAIRE","RÉSEAU","GROUPE"][int(action[1+2*i]*2.99)])

    # Graphique des niveaux
    plt.figure(figsize=(12,5))
    for i, t in enumerate(env.tanks):
        plt.plot(history['levels'][i], label=f'Tank {i+1} Level')
    plt.axhline(y=2, color='r', linestyle='--', label="Seuil Critique")
    plt.title("WIIGA : Niveaux des cuves sur 24h")
    plt.xlabel("Heures")
    plt.ylabel("Niveau (m)")
    plt.legend()
    plt.grid(True)
    plt.show()

if __name__ == "__main__": run_demo()