import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random


# ==========================================================
# ENVIRONMENT: ADD TWO NUMBERS
# ==========================================================

class AddEnv:

	def __init__(self):
		self.max_value = 9

	def reset(self):
		# Random integers between 0 and 9
		self.a = random.randint(0, self.max_value)
		self.b = random.randint(0, self.max_value)

		# State is normalized for better learning stability
		return np.array([self.a / 9.0, self.b / 9.0], dtype=np.float32)

	def step(self, action):

		correct_sum = self.a + self.b

		if action == correct_sum:
			reward = 1.0
		else:
			reward = -1.0

		done = True  # One-step episode
		return None, reward, done


# ==========================================================
# POLICY NETWORK
# ==========================================================

class Policy(nn.Module):

	def __init__(self):
		super().__init__()

		self.model = nn.Sequential(
			nn.Linear(2, 64),
			nn.ReLU(),
			nn.Linear(64, 64),
			nn.ReLU(),
			nn.Linear(64, 19),   # outputs 0–18
			nn.Softmax(dim=-1)
		)

	def forward(self, x):
		return self.model(x)