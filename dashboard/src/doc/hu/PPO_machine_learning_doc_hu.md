# Machine Learning bemenetek és kimenetek

## Koncepció
Egy egyedi PPO-alapú ([Proximal Policy Optimization](https://spinningup.openai.com/en/latest/algorithms/ppo.html)) rover környezet,  
amely a hagyományos Mars rover szimulációra épül, a `stable_baselines3` könyvtár használatával.

Az ML oldal 3 fő részből áll:
- `ppo_shared.py`  
  → Közös bemenet/kimenet struktúra, sebességfokozat konverzió, ásvány rangsorolás és jutalomfüggvény (reward shaping)
- `PPO_model_trainer.py`  
  → PPO tanító környezet és tanítási belépési pont
- `live_rover_test.py`  
  → Betanított modell betöltése és futtatása élő szimulációval + dashboard/szerver logolás

A policy **nem közvetlenül mezőről mezőre mozgatja a rovert**.  
Ehelyett egy normalizált megfigyelési vektort kap, majd kiválasztja:
- a rover sebességfokozatát
- egy cél X koordinátát
- egy cél Y koordinátát

A környezet ezt lefordítja konkrét rover műveletekre (`path_find_to()`, `mine()`).

---

## Bemenetek (Inputs)
Minden megfigyelési érték a `0.0 – 1.0` tartományra van normalizálva.

### Alap adatok
- rover akkumulátor
- rover sebességfokozat
- szimuláció teljes futási ideje (`run_hrs`)
- hátralévő idő
- napszak (idő a ciklusban)
- rover X pozíció
- rover Y pozíció
- korábban bányászott X
- korábban bányászott Y

### Legközelebbi ásványok (N darab)
- távolság (opcionális – elhagyható, ha az AI megtanulja az A* útvonaltervezést)
- X koordináta
- Y koordináta

### Fontos közös függvények
- `obs_size(mineral_count)`  
  → A bemeneti vektor mérete
- `build_obs(world, mineral_count, prev_mined, mineral_cache, obs_buf=None)`  
  → Megfigyelési vektor felépítése
- `rank_minerals(world, mineral_count)`  
  → Legközelebbi ásványok kiválasztása

---

## Kimenetek (Outputs)
A PPO akciótér egy folytonos `Box`, 3 értékkel:

- sebességfokozat beállítása
- cél X pozíció
- cél Y pozíció

> A bányászat automatikusan történik, amikor a rover ásvány mezőre lép.

### Fontos függvény
- `snap_gear(value)`  
  → A nyers modell kimenetet a legközelebbi érvényes fokozatra konvertálja

---

## Tanítás (Training)

### `RoverEnv` osztály
A fő Gymnasium környezet PPO tanításhoz.

#### Konstruktor paraméterek
- `run_hrs`: szimuláció hossza `[float]`
- `delta_hrs`: fix időlépés `[float]`
- `run_hrs_options`: opcionális epizód hossz választék
- `delta_mode`: léptetési mód `[str]`
- `tick_seconds`: valós idejű várakozás `[float]`
- `env_speed`: sebesség szorzó `[float]`
- `map_csv_path`: egyedi térkép `[str | None]`

#### Fontos változók
- `world`: rover világ `[RoverSimulationWorld]`
- `observation_space`: bemeneti tér `[spaces.Box]`
- `action_space`: kimeneti tér `[spaces.Box]`
- `OBS_SIZE`: bemenet méret
- `MINERAL_COUNT`: ásvány slotok száma

#### Függvények
- `reset(...)`  
  → Teljes reset + első megfigyelés
- `step(action)`  
  → Akció alkalmazása, léptetés, jutalom számítás

---

### `MinuteProgressCallback`
Egyszerű callback, amely kiírja a tanulási folyamat állapotát.

---

### Fő tanító függvények
- `build_vec_env(...)`  
  → Több környezet létrehozása
- `train_model(...)`  
  → Modell létrehozása / folytatása, tanítás, mentés
- `main()`  
  → Konzolos belépési pont

---

## Közös jutalom és távolság logika

### Függvények
- `tile_step_distance(a, b)`  
  → Távolság számítása (8 irány)
- `estimate_return_home_hrs(current_pos, start_pos, gear=GEARS.FAST)`  
  → Hazatérés becsült ideje
- `return_focus_window_hrs(current_pos, start_pos, min_window_hrs=5.0)`  
  → Mikor kell hazatérésre váltani
- `compute_reward(...)`  
  → Közös jutalom számítás

### Jutalom elemek
- jutalom bányászatért
- sorozat bónusz (streak)
- büntetés mozgás hiányáért
- büntetés hosszú bányászat nélküli időért
- akkumulátor használati büntetés
- hazatérés fókusz az epizód végén

---

## Élő futtatás (Live inference)

### `LivePolicyEnv` osztály
Könnyű wrapper élő modell futtatáshoz.

#### Konstruktor paraméterek
- `run_hrs`: szimuláció hossza
- `mineral_count`: modell által várt ásvány slotok száma
- `delta_mode`: léptetés mód
- `set_delta_hrs`: fix lépés
- `tick_seconds`: valós várakozás
- `env_speed`: sebesség szorzó
- `base_url`: backend URL
- `send_every`: küldési gyakoriság
- `map_csv_path`: térkép

#### Fontos változók
- `world`: rover világ
- `obs_size`: bemenet méret
- `mineral_count`: ásvány slotok száma

#### Függvények
- `obs()`  
  → Aktuális bemenet generálása
- `step(action)`  
  → Akció végrehajtása
- `reward(...)`  
  → Jutalom újraszámítása debug célra

---

## Élő futtató függvények
- `choose_model_base(requested)`  
  → Modell kiválasztása
- `infer_mineral_count(model)`  
  → Ásvány slot szám visszakövetkeztetése
- `main()`  
  → Konzolos futtatás