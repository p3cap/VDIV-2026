"""DQN helper library used by the MarsRover project.

This file provides:
1) A replay buffer for storing transitions.
2) A feed-forward Q-network.
3) A DQN agent with epsilon-greedy action selection.
4) A trainer that runs the train/eval loops.
"""

import random  # Random sampling for replay and epsilon-greedy exploration.
import collections  # Efficient fixed-size queue (deque) for experience replay.
from typing import Optional, Sequence  # Type hints for optional values and layer size lists.
import numpy as np  # Numeric array operations for states and mini-batches.
import torch  # PyTorch base package (tensors, devices, serialization).
import torch.nn as nn  # Neural network layers and loss functions.
import torch.optim as optim  # Optimizers (Adam).


# Replay buffer stores transitions and returns random mini-batches.
class ReplayBuffer:
    def __init__(self, capacity: int):
        # Maximum number of transitions to keep in memory.
        self.capacity = int(capacity)
        # Deque with maxlen auto-drops oldest entries when full.
        self.buffer = collections.deque(maxlen=self.capacity)

    def push(self, state, action, reward, next_state, done):
        # Store one experience tuple: (s, a, r, s', done).
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int):
        # Uniformly sample without replacement from stored experiences.
        batch = random.sample(self.buffer, batch_size)
        # Unzip list of tuples into tuple of lists for each field.
        states, actions, rewards, next_states, dones = zip(*batch)
        # Convert fields into numpy arrays suitable for tensor conversion.
        return (
            np.stack(states),
            np.array(actions),
            np.array(rewards, dtype=np.float32),
            np.stack([ns if ns is not None else np.zeros_like(states[0]) for ns in next_states]),
            np.array(dones, dtype=np.uint8),
        )

    def __len__(self):
        # Allows len(replay_buffer) usage.
        return len(self.buffer)


# Simple multi-layer perceptron that predicts Q-values for each action.
class QNetwork(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, hidden_sizes: Sequence[int] = (64, 64)):
        # Initialize PyTorch nn.Module internals.
        super().__init__()
        # Build layer list dynamically from hidden_sizes.
        layers = []
        # Track current input size for each appended Linear layer.
        last = input_dim
        # Add hidden blocks: Linear -> ReLU.
        for h in hidden_sizes:
            layers.append(nn.Linear(last, h))
            layers.append(nn.ReLU())
            last = h
        # Add final projection to action space (Q-value per action).
        layers.append(nn.Linear(last, output_dim))
        # Wrap list into a single callable module.
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Standard forward pass through the stacked layers.
        return self.net(x)


# DQN agent contains behavior and target networks plus optimization logic.
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
        # Use user-provided device or auto-select CUDA when available.
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        # Save state vector size.
        self.state_dim = state_dim
        # Save number of discrete actions.
        self.action_dim = action_dim
        # Discount factor for future rewards.
        self.gamma = gamma

        # Online network used for action selection and gradient updates.
        self.q_net = QNetwork(state_dim, action_dim, hidden_sizes).to(self.device)
        # Target network used for stable TD targets.
        self.target_q_net = QNetwork(state_dim, action_dim, hidden_sizes).to(self.device)
        # Initialize target network weights to match online network.
        self.target_q_net.load_state_dict(self.q_net.state_dict())
        # Adam optimizer updates only the online network parameters.
        self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr)

    def act(self, state: np.ndarray, epsilon: float) -> int:
        # Epsilon-greedy: with probability epsilon, choose random action.
        if random.random() < epsilon:
            return random.randrange(self.action_dim)
        # Convert 1D numpy state to batched float tensor [1, state_dim].
        st = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        # No gradients needed for inference-time action selection.
        with torch.no_grad():
            # Compute Q-values for each action.
            q = self.q_net(st)
            # Pick action index with highest Q-value.
            return int(torch.argmax(q, dim=1).item())

    def save(self, path: str):
        # Persist online network weights to disk.
        torch.save(self.q_net.state_dict(), path)

    def load(self, path: str):
        # Load online network weights and map tensors to active device.
        self.q_net.load_state_dict(torch.load(path, map_location=self.device))
        # Keep target network synchronized after loading.
        self.target_q_net.load_state_dict(self.q_net.state_dict())

    def update_target(self):
        # Hard update: copy online network weights into target network.
        self.target_q_net.load_state_dict(self.q_net.state_dict())

    def learn_from_batch(self, batch, batch_size: int, loss_fn=nn.MSELoss()):
        # Unpack replay mini-batch components.
        states, actions, rewards, next_states, dones = batch
        # Convert numpy arrays to tensors on the training device.
        states_v = torch.FloatTensor(states).to(self.device)
        next_states_v = torch.FloatTensor(next_states).to(self.device)
        actions_v = torch.LongTensor(actions).to(self.device)
        rewards_v = torch.FloatTensor(rewards).to(self.device)
        dones_v = torch.FloatTensor(dones).to(self.device)

        # Predicted Q(s, a) from online network for chosen action indices.
        q_values = self.q_net(states_v)
        q_value = q_values.gather(1, actions_v.unsqueeze(1)).squeeze(1)

        # Compute max_a' Q_target(s', a') without gradient tracking.
        with torch.no_grad():
            next_q_values = self.target_q_net(next_states_v)
            max_next_q = next_q_values.max(1)[0]

        # Bellman target: r + gamma * max_next_q for non-terminal transitions.
        target = rewards_v + (1.0 - dones_v) * self.gamma * max_next_q
        # Regression loss between predicted and target Q-values.
        loss = loss_fn(q_value, target)

        # Standard optimization step.
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        # Return scalar loss for logging/monitoring.
        return loss.item()


# Trainer orchestrates environment interaction, replay updates, and evaluation.
# Expected environment API:
# reset() -> state (np.ndarray)
# step(action) -> (next_state np.ndarray or None, reward float, done bool)
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
        # External environment object implementing reset() and step().
        self.env = env
        # DQN agent to train/evaluate.
        self.agent = agent
        # Replay memory with fixed maximum capacity.
        self.replay = ReplayBuffer(buffer_size)
        # Number of transitions per optimization step.
        self.batch_size = batch_size
        # Warm-up steps parameter kept for compatibility/tuning.
        self.initial_exploration = initial_exploration
        # Frequency (in env steps) of gradient updates.
        self.train_frequency = train_frequency
        # Frequency (in env steps) of target network sync.
        self.target_update_freq = target_update_freq
        # Minimum replay size required before learning starts.
        self.min_buffer_size_to_learn = min_buffer_size_to_learn
        # Global step counter across all episodes.
        self.total_steps = 0

    def _store_transition(self, s, a, r, ns, done):
        # Store transition; keep None for terminal next_state if provided.
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
        # Initialize exploration rate.
        eps = epsilon_start
        # Track training curve and periodic evaluation scores.
        stats = {"episode": [], "avg_reward": [], "eval_acc": []}

        # Main episode loop.
        for ep in range(1, max_episodes + 1):
            # Reset environment to start a new episode.
            s = self.env.reset()
            # Episode reward accumulator.
            ep_reward = 0.0

            # Step loop within one episode.
            for step in range(max_steps_per_episode):
                # Choose action with epsilon-greedy policy.
                a = self.agent.act(s, eps)
                # Execute action in environment.
                ns, r, done = self.env.step(a)

                # Keep None next_state for terminal transitions.
                next_state_for_storage = ns if ns is not None else None
                # Push current transition into replay memory.
                self._store_transition(s, a, r, next_state_for_storage, float(done))
                # Move to next state; if None, keep previous state placeholder.
                s = ns if ns is not None else s
                # Add immediate reward to episode total.
                ep_reward += r
                # Increment global environment step counter.
                self.total_steps += 1

                # Train only after enough replay data is available.
                if len(self.replay) >= self.min_buffer_size_to_learn and (self.total_steps % self.train_frequency == 0):
                    # Sample random mini-batch and do one gradient step.
                    batch = self.replay.sample(self.batch_size)
                    self.agent.learn_from_batch(batch, self.batch_size)

                # Periodically sync target network weights.
                if self.total_steps % self.target_update_freq == 0:
                    self.agent.update_target()

                # End current episode if environment signals terminal.
                if done:
                    break

            # Exponentially decay epsilon, bounded by epsilon_final.
            if eps > epsilon_final:
                eps = max(epsilon_final, eps * epsilon_decay)

            # Print coarse-grained progress logs.
            if verbose and (ep % max(1, max_episodes // 20) == 0 or ep == 1):
                print(f"[Train] Ep {ep}/{max_episodes} | EpReward {ep_reward:.3f} | Eps {eps:.3f} | Buffer {len(self.replay)}")

            # Store training statistics for plotting/analysis.
            stats["episode"].append(ep)
            stats["avg_reward"].append(ep_reward)

            # Run evaluation at configured intervals.
            if eval_every > 0 and ep % eval_every == 0:
                acc = self.evaluate(eval_episodes)
                stats["eval_acc"].append(acc)
                if verbose:
                    print(f"  -> {ep} Eval accuracy (over {eval_episodes} episodes): {acc*100:.2f}%")
                # Early-stop for toy tasks when perfect accuracy is reached.
                if acc == 1.0:
                    if verbose:
                        print("Reached 100% evaluation accuracy. Stopping training.")
                    break

        # Return collected training/evaluation metrics.
        return stats

    def evaluate(self, episodes: int = 100) -> float:
        # Evaluate with greedy policy; success definition is task-specific.
        success = 0
        total = 0
        # Run a fixed number of one-step evaluation episodes.
        for _ in range(episodes):
            # Reset environment and get initial state.
            s = self.env.reset()
            # Greedy action selection (epsilon=0).
            a = self.agent.act(s, epsilon=0.0)
            # Apply action and observe reward/outcome.
            ns, r, done = self.env.step(a)
            # Count success when reward is positive.
            if r > 0:
                success += 1
            # Count total evaluated episodes.
            total += 1
        # Return success fraction; safe-guard division by zero.
        return success / total if total > 0 else 0.0
