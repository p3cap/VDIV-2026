# ML Inputs, outputs
## Inputs:
*Find out how to send lists thru nodes, optimised*
*nodes can only have value 0-1*

- pos x
- pos y
- battery
- gear (0,0.5,1)
- run_hrs
- time of day

- closest mineral 1 - pos x
- closest mineral 1 - pos y
- closest mineral 1 - distance

- closest mineral 2 - pos x
- closest mineral 2 - pos y
- closest mineral 2 - distance

- closest mineral 3 - pos x
- closest mineral 3 - pos y
- closest mineral 3 - distance

... futtatok rá tesztet mennyi a legoptimálisabb mennyiség (szerintem olyan 30 körül)

## Ouputs
- set_gear (0,1,2)
- goto mineral (index 1-30)
- mine (0-1)

