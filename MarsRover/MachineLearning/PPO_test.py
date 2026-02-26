"""
PPO Training Script for Mars Rover
Uses stable_baselines3 PPO with multiprocessing and monitoring.
Configuration from ML_config.md
"""

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv, Monitor
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
import torch
import os
from pathlib import Path
import numpy as np

from RoverEnv import RoverEnv


# ==================== CONFIGURATION ====================
# Based on ML_config.md specifications

# Training parameters
TOTAL_TIMESTEPS = 100000  # Total environment steps
NUM_ENVS = 4  # Number of parallel environments
LEARNING_RATE = 3e-4
N_STEPS = 2048  # Steps per environment per update
BATCH_SIZE = 64
N_EPOCHS = 10
GAMMA = 0.99  # Discount factor
GAE_LAMBDA = 0.95
CLIP_RANGE = 0.2
ENT_COEF = 0.0  # Entropy coefficient
VF_COEF = 0.5

# Environment parameters
MAP_PATH = Path(__file__).parent.parent / "data" / "mars_map_50x50.csv"
RUN_HRS = 24.0
MAX_STEPS_PER_EPISODE = 1000
SIM_TIME_MULTIPLIER = 1.0

# Output paths
TRAINED_DIR = Path(__file__).parent / "trained"
MODEL_NAME = "rover_ppo"
MODEL_PATH = TRAINED_DIR / MODEL_NAME
LOGS_DIR = Path(__file__).parent / "logs"

# ==================== SETUP ====================


def make_env(env_id: int) -> RoverEnv:
	"""Factory function to create an environment instance."""
	def _init():
		env = RoverEnv(
			map_path=str(MAP_PATH),
			run_hrs=RUN_HRS,
			max_steps=MAX_STEPS_PER_EPISODE,
			sim_multiplier=SIM_TIME_MULTIPLIER,
		)
		return Monitor(env, str(LOGS_DIR / f"env_{env_id}"), allow_episode_resets=True)
	
	return _init


def setup_directories():
	"""Create necessary directories."""
	TRAINED_DIR.mkdir(parents=True, exist_ok=True)
	LOGS_DIR.mkdir(parents=True, exist_ok=True)


def create_vectorized_env(num_envs: int):
	"""Create a vectorized environment with SubprocVecEnv."""
	env_fns = [make_env(i) for i in range(num_envs)]
	vec_env = SubprocVecEnv(env_fns)
	return vec_env


def create_ppo_model(vec_env):
	"""Create and return a PPO model."""
	model = PPO(
		policy="MlpPolicy",
		env=vec_env,
		learning_rate=LEARNING_RATE,
		n_steps=N_STEPS,
		batch_size=BATCH_SIZE,
		n_epochs=N_EPOCHS,
		gamma=GAMMA,
		gae_lambda=GAE_LAMBDA,
		clip_range=CLIP_RANGE,
		ent_coef=ENT_COEF,
		vf_coef=VF_COEF,
		max_grad_norm=0.5,
		use_sde=False,
		device="cuda" if torch.cuda.is_available() else "cpu",
		verbose=1,
	)
	return model


# ==================== CALLBACKS ====================


class CustomCallback:
	"""Callback for logging training progress."""
	
	def __init__(self, check_freq: int = 5000):
		self.check_freq = check_freq
		self.calls = 0
	
	def __call__(self, locals_, globals_):
		self.calls += 1
		if self.calls % (self.check_freq // 2048) == 0:
			model = locals_["self"]
			print(
				f"\nTimestep: {model.num_timesteps} / {TOTAL_TIMESTEPS}\n"
				f"Progress: {100 * model.num_timesteps / TOTAL_TIMESTEPS:.1f}%"
			)
		return True


# ==================== MAIN TRAINING ====================


def train():
	"""Main training function."""
	print("=" * 60)
	print("Mars Rover PPO Training")
	print("=" * 60)
	
	# Setup
	setup_directories()
	
	print(f"\n📊 Configuration:")
	print(f"  Total timesteps: {TOTAL_TIMESTEPS}")
	print(f"  Parallel environments: {NUM_ENVS}")
	print(f"  Learning rate: {LEARNING_RATE}")
	print(f"  Batch size: {BATCH_SIZE}")
	print(f"  Device: {torch.device('cuda' if torch.cuda.is_available() else 'cpu')}")
	print(f"  Map: {MAP_PATH}")
	
	# Create vectorized environment
	print(f"\n🌍 Creating vectorized environment ({NUM_ENVS} parallel envs)...")
	vec_env = create_vectorized_env(NUM_ENVS)
	
	# Create PPO model
	print(f"🤖 Creating PPO model...")
	model = create_ppo_model(vec_env)
	
	# Callbacks
	checkpoint_callback = CheckpointCallback(
		save_freq=5000,
		save_path=TRAINED_DIR,
		name_prefix="rover_ppo_checkpoint",
	)
	
	print(f"\n▶️  Starting training ({TOTAL_TIMESTEPS} steps)...")
	print("-" * 60)
	
	try:
		# Train the model
		model.learn(
			total_timesteps=TOTAL_TIMESTEPS,
			callback=checkpoint_callback,
			progress_bar=True,
		)
		
		# Save the final model
		print(f"\n✅ Training complete!")
		print(f"💾 Saving model to {MODEL_PATH}...")
		model.save(str(MODEL_PATH))
		
		print(f"✨ Model saved successfully!")
		print(f"   Path: {MODEL_PATH}")
		
	except KeyboardInterrupt:
		print("\n⚠️  Training interrupted by user")
		print(f"💾 Saving checkpoint...")
		model.save(str(TRAINED_DIR / "rover_ppo_interrupted"))
	
	finally:
		vec_env.close()


def evaluate(num_episodes: int = 5):
	"""Evaluate a trained model."""
	print("\n" + "=" * 60)
	print("Mars Rover PPO Evaluation")
	print("=" * 60)
	
	if not MODEL_PATH.exists():
		print(f"❌ Model not found at {MODEL_PATH}")
		return
	
	print(f"📂 Loading model from {MODEL_PATH}...")
	model = PPO.load(str(MODEL_PATH))
	
	# Create evaluation environment
	print(f"🌍 Creating evaluation environment...")
	env = RoverEnv(
		map_path=str(MAP_PATH),
		run_hrs=RUN_HRS,
		max_steps=MAX_STEPS_PER_EPISODE,
		sim_multiplier=SIM_TIME_MULTIPLIER,
	)
	
	print(f"\n▶️  Running {num_episodes} evaluation episodes...")
	print("-" * 60)
	
	total_rewards = []
	total_minerals = []
	total_distances = []
	
	for episode in range(num_episodes):
		obs, info = env.reset()
		done = False
		episode_reward = 0.0
		episode_minerals = 0
		
		while not done:
			action, _states = model.predict(obs, deterministic=True)
			obs, reward, terminated, truncated, info = env.step(action)
			episode_reward += reward
			episode_minerals = info["minerals_collected"]
			done = terminated or truncated
		
		total_rewards.append(episode_reward)
		total_minerals.append(episode_minerals)
		total_distances.append(info["distance_travelled"])
		
		print(
			f"Episode {episode + 1:2d} | "
			f"Reward: {episode_reward:8.2f} | "
			f"Minerals: {episode_minerals:2d} | "
			f"Distance: {info['distance_travelled']:3d}"
		)
	
	env.close()
	
	# Summary statistics
	print("-" * 60)
	print(f"\n📈 Evaluation Summary:")
	print(f"  Avg Reward: {np.mean(total_rewards):.2f} ± {np.std(total_rewards):.2f}")
	print(f"  Avg Minerals: {np.mean(total_minerals):.1f} ± {np.std(total_minerals):.1f}")
	print(f"  Avg Distance: {np.mean(total_distances):.1f} ± {np.std(total_distances):.1f}")


# ==================== ENTRY POINT ====================


if __name__ == "__main__":
	import sys
	
	if len(sys.argv) > 1 and sys.argv[1] == "eval":
		evaluate(num_episodes=5)
	else:
		train()
		print("\n💡 To evaluate the model, run: python PPO_test.py eval")
