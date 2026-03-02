import argparse
import sys
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO

MARS_ROVER_ROOT = Path(__file__).resolve().parent.parent
if str(MARS_ROVER_ROOT) not in sys.path:
    sys.path.append(str(MARS_ROVER_ROOT))

from PPO_test import RoverSimpleEnv


def test_model(model_path: str, num_episodes: int = 5, render: bool = False):
    """Test a trained PPO model on the rover environment."""
    
    # Load the trained model
    model = PPO.load(model_path)
    env = RoverSimpleEnv()
    
    episode_rewards = []
    episode_minerals = []
    episode_steps = []
    
    print(f"\nTesting model: {model_path}")
    print(f"Running {num_episodes} episodes...\n")
    
    for episode in range(num_episodes):
        obs, _ = env.reset()
        done = False
        episode_reward = 0.0
        steps = 0
        initial_minerals = len(env._all_minerals())
        
        while not done:
            # Use the trained model to predict action
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(action)
            episode_reward += reward
            steps += 1
            done = terminated or truncated
        
        # Count mined minerals
        minerals_mined = initial_minerals - len(env._all_minerals())
        episode_rewards.append(episode_reward)
        episode_minerals.append(minerals_mined)
        episode_steps.append(steps)
        
        print(f"Episode {episode + 1}/{num_episodes}")
        print(f"  Reward: {episode_reward:.2f}")
        print(f"  Minerals Mined: {minerals_mined}/{initial_minerals}")
        print(f"  Steps: {steps}")
        print(f"  Battery: {env.rover.battery:.1f}/{env.rover.MAX_BATTERY_CHARGE}")
        print()
    
    # Print statistics
    print("=" * 50)
    print("STATISTICS")
    print("=" * 50)
    print(f"Average Reward: {np.mean(episode_rewards):.2f} (±{np.std(episode_rewards):.2f})")
    print(f"Average Minerals Mined: {np.mean(episode_minerals):.2f}")
    print(f"Average Steps per Episode: {np.mean(episode_steps):.1f}")
    print(f"Max Reward: {np.max(episode_rewards):.2f}")
    print(f"Min Reward: {np.min(episode_rewards):.2f}")
    print("=" * 50)
    
    env.close()


def main():
    parser = argparse.ArgumentParser(description="Test a trained PPO rover model.")
    parser.add_argument(
        "--model",
        type=str,
        default=str(MARS_ROVER_ROOT / "MachineLearning" / "trained" / "rover_ppo_simple"),
        help="Path to the trained model (without .zip extension)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=5,
        help="Number of episodes to test",
    )
    args = parser.parse_args()
    
    test_model(args.model, num_episodes=args.episodes)


if __name__ == "__main__":
    main()
