# ML Inputs, outputs
## concept:
Cutom rover env
give rover basic info
for ML optimistion the DQN will get the closest n amount of ores
and can order the rover to move to the given ore.

## Inputs:
*Find out how to send lists thru nodes, optimised*
*nodes can only have value 0-1*

- battery
- gear (0,0.5,1)
- run_hrs 
- time of day
- rover x
- rover y
- previoulsy mined x
- previoulsy mined y


- closest mineral 1 - distance
- closest mineral 1 - x
- closest mineral 1 - y
- closest mineral 2 - distance
- closest mineral 2 - x
- closest mineral 2 - y
- closest mineral 3 - distance
- closest mineral 3 - x
- closest mineral 3 - y
- ...

... futtatok rá tesztet mennyi a legoptimálisabb mennyiség (szerintem olyan 30 körül)

## Ouputs
- set_gear (0,1,2)
- goto mineral (index 1-30)
- mine (0-1)

