# Brockton Bay

An online text RPG for the Kuznya engine, set in the world of [Worm](https://parahumans.wordpress.com/) by
Wildbow. April 2011: a dying port city, three gangs, a hero team on an oil rig, and you - nobody in
particular, just off the bus with $60 and two loaves of bread.

This is an unofficial, non-commercial fan work. Worm, its setting and its characters belong to Wildbow.
Nothing here reproduces text from the serial.

## Play

```bash
pip install -r requirements.txt
cp games/worm/brockton_bay.wrld my_city.wrld      # the server saves its state back into the file it runs
python interpreter/src/main.py my_city.wrld
```

Open http://localhost:1339. Pick a name and a password; the same name and password bring the same
character back later. `help` lists the commands.

A prebuilt world is also attached to the [releases](../../../../releases) of this repository.

To let other people in, set the bind address to `0.0.0.0` (editor: Server tab, or the MCP tool
`server_settings host=0.0.0.0`) and open ports 1337 and 1339. The connection is plain `ws://`:
passwords are stored hashed but travel unencrypted, so do not reuse a real one.

## What is simulated

About 255 residents live in 59 places. Nobody stands still waiting for a player.

- **Everyone has a job, a home, needs and a temper.** Bakers start at four, dockworkers at six, bartenders
  at four in the afternoon. People get hungry and buy the cheapest food they can reach, sleep, drink, gamble,
  gossip, make friends, go to hospital when hurt, and steal or mug when desperate.
- **Everyone has a task they do first.** Each morning a resident gets one out of their job and
  relationships: report to the boss, give the staff their orders, ask a business for work, collect
  protection money, give a child lunch money, catch up with a friend. Some of those tasks are aimed at you:
  the union rep looks for the unemployed, your boss comes to find you, a stranger asks you to carry a parcel,
  a recruiter turns up when you are broke - or after you trigger.
- **The economy is not scripted.** Flour is unloaded at the Cargo Pier, hauled to the bakery, baked, hauled
  to the market and sold by whoever is behind the counter. Prices follow stock; wages come out of the till;
  an unpaid worker walks out after three days; the unemployed ask around for openings and start unskilled.
  Kill the bakers and bread gets expensive until replacements learn the trade. `market` shows it happening.
- **Powers come from the worst day of your life.** Being beaten half to death, cornered, outnumbered,
  starving, or standing too close to a cape fight can cause a trigger event. The kind of danger steers the
  classification, the way it does in the source. Powers are generated: twelve PRT classifications, 34
  archetypes, 40 themes, ratings from 1 to 12. Most are street level, some are jokes
  ("it only works while you hold your breath"), a few are monsters. A third of new powers echo one listed on
  the Worm wiki. Residents can trigger too, and then choose a side.
- **67 canon parahumans** live double lives with their wiki classifications and ratings: Armsmaster and the
  Protectorate, the Wards at Arcadia, New Wave, the Empire behind Medhall, Lung's ABB, the Merchants, the
  Undersiders in their loft, Coil, Faultline's Crew at the Palanquin. Taylor Hebert goes to Winslow by day.
  Heroes patrol and answer incidents; gangs extort shops, recruit the unemployed, mug people on their turf
  and raid each other; villains break out of custody as often as they do in canon.
- **Dated events set things in motion** and the simulation decides how they end: Lung gathering the ABB on
  the night of 10 April, the Undersiders at Brockton Bay Central Bank on the 14th, the Empire's absent capes
  returning on the 15th, the Travelers arriving, Bakuda's bombing campaign, and Leviathan on 15 May.

## Commands

```
look · go <place or number> · where <place> · map · time · who
examine <name> · talk <name> · say <text> · give <name> <amount|item>
status · inv · eat · buy [n] <item> · sell [n] <item> · prices · market · rest
jobs · apply · work · stop · quit · tasks · accept
attack <name> · flee · pay · steal <item> · call · join <group>
power · power <ability> [target or place] · news
```

## How it is built

Everything in the world file was created through the engine's MCP server, with the same tools an AI agent
uses (see [AGENTS.md](../../AGENTS.md)):

```bash
pip install mcp
python games/worm/build.py
```

| | |
|---|---|
| `scripts/` | The game: 13 library scripts loaded with `world.require`, and four scripts attached to objects (`Director`, `Person`, `Business`, `Player`) |
| `data/canon_research.json` | Characters, places, classifications, power examples and timeline collected from the Worm wiki; entries say whether they were verified there |
| `data/city_data.py` | The map and the businesses. Places the serial implies but never names (a bakery, the working piers, a police precinct) are marked generic |
| `client.html` | The web client |
| `simulate.py` | Runs the city headless, fast, and prints prices, deaths and crime day by day |

```bash
python games/worm/simulate.py --days 16 --kill baker --on 4     # bread after the bakers die
python games/worm/simulate.py --days 6 --leviathan 1            # the week after an Endbringer
python tests/play_worm.py                                       # plays the game as a player, over MCP
```

Three parts of the game are exported as assets in [`assets/`](../../assets) and can be loaded into any other
Kuznya project: `economy.kasset`, `parahuman_powers.kasset` and `citizen.kasset` (the resident prefab with
its whole decision loop).
