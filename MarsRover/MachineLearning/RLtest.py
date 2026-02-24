# train_until_perfect.py

import torch
import torch.nn as nn
import torch.optim as optim
import itertools
from ReinforcedLearning import Policy

# Terminal color helper
class Colors:
    GREEN = "\033[92m"
    END = "\033[0m"

# -------------------------
# Prepare dataset (all sums 0-9)
# -------------------------
X = []
Y = []
for a, b in itertools.product(range(10), repeat=2):
    X.append([a / 9.0, b / 9.0])
    Y.append(a + b)

X = torch.FloatTensor(X)
Y = torch.LongTensor(Y)

# -------------------------
# Network and optimizer
# -------------------------
policy = Policy()
optimizer = optim.Adam(policy.parameters(), lr=0.01)
criterion = nn.CrossEntropyLoss()

# -------------------------
# Training until 100% accuracy
# -------------------------
epoch = 0
while True:
    logits = policy(X)
    loss = criterion(logits, Y)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    # Evaluate accuracy
    with torch.no_grad():
        preds = torch.argmax(logits, dim=1)
        correct = (preds == Y).sum().item()
        acc = correct / len(Y) * 100

    # Print progress every 50 epochs
    if epoch % 50 == 0:
        acc_str = f"{Colors.GREEN}{acc:.2f}%{Colors.END}" if acc == 100 else f"{acc:.2f}%"
        print(f"Epoch {epoch} | Loss: {loss.item():.4f} | Accuracy: {acc_str}")

    epoch += 1

    # Stop when accuracy is 100%
    if acc == 100:
        print(f"\nReached perfect accuracy at epoch {epoch}!")
        break

# Save final model
torch.save(policy.state_dict(), "add_policy_weights.pth")
print("Model saved as add_policy_weights.pth")

# -------------------------
# Interactive test
# -------------------------
policy.eval()
print("\n=== Interactive Test ===")
print("Enter two numbers 0-9 separated by space. Type 'q' to quit.")

while True:
    try:
        inp = input("Input: ")
        if inp.lower() == 'q':
            break

        a_str, b_str = inp.strip().split()
        a = int(a_str)
        b = int(b_str)
        if not (0 <= a <= 9 and 0 <= b <= 9):
            print("Numbers must be 0-9")
            continue

        state = torch.FloatTensor([a / 9.0, b / 9.0])
        with torch.no_grad():
            probs = policy(state)
            pred = torch.argmax(probs).item()

        correct_sum = a + b
        if pred == correct_sum:
            print(f"Model predicts: {Colors.GREEN}{a} + {b} = {pred}{Colors.END}")
        else:
            print(f"Model predicts: {a} + {b} = {pred} (correct: {correct_sum})")

    except Exception:
        print("Invalid input. Enter two integers 0-9 separated by space, or 'q' to quit.")