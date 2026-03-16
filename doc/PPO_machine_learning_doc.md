# UNFINISHED

# Mars Rover Machine Learning Documentation
- [Concept](#concept)
- [NN Structure](#nn-structure)


## concept:
Using a PPO ([Proximal Policy Optimization](https://spinningup.openai.com/en/latest/algorithms/ppo.html)) based machine learning with the usage of the [stable_baselines3](https://github.com/DLR-RM/stable-baselines3) library.


## NN Structure
### Inputs:

- rover battery
- rover gear
- simulation run hours 
- simulation tod
- rover x pos
- rover y pos
- previoulsy mined ore x pos
- previoulsy mined ore y pos
- n amounts of ore data
  - closest ore n - path finding distance
  - closest ore n - x pos
  - closest ore n - y pos

### Ouputs
- set gear
- goto pos x
- goto pos y

### Functions
Autmatically mines the given tile if the rover landed on top of it.

## Usage


