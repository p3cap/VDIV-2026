#
#
#
#
#
#
#

import random
import collections
from typing import Tuple, Optional, Sequence
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


# ---------------------------
# Replay buffer (simple)
# ---------------------------
class ReplayBuffer:
    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self.buffer = collections.deque(maxlen=self.capacity)

    def push(self, state, action, reward, next_state, done):
        # store raw numpy arrays / scalars
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (np.stack(states), np.array(actions), np.array(rewards, dtype=np.float32),
                np.stack([ns if ns is not None else np.zeros_like(states[0]) for ns in next_states]),
                np.array(dones, dtype=np.uint8))

    def __len__(self):
        return len(self.buffer)


# ---------------------------
# Generic Q-network
# ---------------------------
class QNetwork(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, hidden_sizes: Sequence[int] = (64, 64)):
        super().__init__()
        layers = []
        last = input_dim
        for h in hidden_sizes:
            layers.append(nn.Linear(last, h))
            layers.append(nn.ReLU())
            last = h
        layers.append(nn.Linear(last, output_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ---------------------------
# DQN Agent (encapsulates nets and policy)
# ---------------------------
class DQNAgent:
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        lr: float = 1e-3,
        gamma: float = 0.99,
        device: Optional[str] = None,
        hidden_sizes: Sequence[int] = (64, 64),
    ):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma

        self.q_net = QNetwork(state_dim, action_dim, hidden_sizes).to(self.device)
        self.target_q_net = QNetwork(state_dim, action_dim, hidden_sizes).to(self.device)
        self.target_q_net.load_state_dict(self.q_net.state_dict())
        self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr)

    def act(self, state: np.ndarray, epsilon: float) -> int:
        # state: numpy array (state_dim,)
        if random.random() < epsilon:
            return random.randrange(self.action_dim)
        st = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q = self.q_net(st)
            return int(torch.argmax(q, dim=1).item())

    def save(self, path: str):
        torch.save(self.q_net.state_dict(), path)

    def load(self, path: str):
        self.q_net.load_state_dict(torch.load(path, map_location=self.device))
        self.target_q_net.load_state_dict(self.q_net.state_dict())

    def update_target(self):
        self.target_q_net.load_state_dict(self.q_net.state_dict())

    def learn_from_batch(self, batch, batch_size: int, loss_fn=nn.MSELoss()):
        states, actions, rewards, next_states, dones = batch
        states_v = torch.FloatTensor(states).to(self.device)
        next_states_v = torch.FloatTensor(next_states).to(self.device)
        actions_v = torch.LongTensor(actions).to(self.device)
        rewards_v = torch.FloatTensor(rewards).to(self.device)
        dones_v = torch.FloatTensor(dones).to(self.device)

        # Q(s,a)
        q_values = self.q_net(states_v)
        q_value = q_values.gather(1, actions_v.unsqueeze(1)).squeeze(1)

        # max_a' Q_target(s', a')
        with torch.no_grad():
            next_q_values = self.target_q_net(next_states_v)
            max_next_q = next_q_values.max(1)[0]

        target = rewards_v + (1.0 - dones_v) * self.gamma * max_next_q

        loss = loss_fn(q_value, target)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item()


# ---------------------------
# Trainer (handles environment, replay, training loop)
# Expected environment API:
#   reset() -> state (np.array)
#   step(action) -> (next_state (np.array) or None, reward (float), done (bool))
# ---------------------------
class DQNTrainer:
    def __init__(
        self,
        env,
        agent: DQNAgent,
        buffer_size: int = 10000,
        batch_size: int = 64,
        initial_exploration: int = 500,
        train_frequency: int = 1,
        target_update_freq: int = 500,
        min_buffer_size_to_learn: int = 500,
    ):
        self.env = env
        self.agent = agent
        self.replay = ReplayBuffer(buffer_size)
        self.batch_size = batch_size
        self.initial_exploration = initial_exploration
        self.train_frequency = train_frequency
        self.target_update_freq = target_update_freq
        self.min_buffer_size_to_learn = min_buffer_size_to_learn
        self.total_steps = 0

    def _store_transition(self, s, a, r, ns, done):
        # normalize None next state to None (ReplayBuffer expects numpy arrays; we encode None as None)
        self.replay.push(s, a, r, ns if ns is not None else None, done)

    def train(
        self,
        max_episodes: int = 2000,
        max_steps_per_episode: int = 1,
        epsilon_start: float = 1.0,
        epsilon_final: float = 0.05,
        epsilon_decay: float = 0.995,
        verbose: bool = True,
        eval_every: int = 100,
        eval_episodes: int = 100,
    ):
        eps = epsilon_start
        stats = {"episode": [], "avg_reward": [], "eval_acc": []}

        for ep in range(1, max_episodes + 1):
            s = self.env.reset()
            ep_reward = 0.0

            for step in range(max_steps_per_episode):
                a = self.agent.act(s, eps)
                ns, r, done = self.env.step(a)

                # handle ns None -> set to zero-array placeholder for storage
                next_state_for_storage = ns if ns is not None else None
                self._store_transition(s, a, r, next_state_for_storage, float(done))
                s = ns if ns is not None else s
                ep_reward += r
                self.total_steps += 1

                # learning step
                if len(self.replay) >= self.min_buffer_size_to_learn and (self.total_steps % self.train_frequency == 0):
                    batch = self.replay.sample(self.batch_size)
                    self.agent.learn_from_batch(batch, self.batch_size)

                # update target network
                if self.total_steps % self.target_update_freq == 0:
                    self.agent.update_target()

                if done:
                    break

            # epsilon decay
            if eps > epsilon_final:
                eps = max(epsilon_final, eps * epsilon_decay)

            if verbose and (ep % max(1, max_episodes // 20) == 0 or ep == 1):
                print(f"[Train] Ep {ep}/{max_episodes} | EpReward {ep_reward:.3f} | Eps {eps:.3f} | Buffer {len(self.replay)}")

            stats["episode"].append(ep)
            stats["avg_reward"].append(ep_reward)

            # evaluation
            if eval_every > 0 and ep % eval_every == 0:
                acc = self.evaluate(eval_episodes)
                stats["eval_acc"].append(acc)
                if verbose:
                    print(f"  -> {ep} Eval accuracy (over {eval_episodes} episodes): {acc*100:.2f}%")
                # Stop early if perfect (useful for toy tasks)
                if acc == 1.0:
                    if verbose:
                        print("Reached 100% evaluation accuracy. Stopping training.")
                    break

        return stats

    def evaluate(self, episodes: int = 100) -> float:
        # returns fraction of episodes where agent predicted correct outcome for tasks like addition
        success = 0
        total = 0
        for _ in range(episodes):
            s = self.env.reset()
            a = self.agent.act(s, epsilon=0.0)  # greedy
            ns, r, done = self.env.step(a)
            # treat reward>0 as success (task-specific)
            if r > 0:
                success += 1
            total += 1
        return success / total if total > 0 else 0.0