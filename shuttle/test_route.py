from gedeeld import ParcoursKaart, RoutePlanner

kaart = ParcoursKaart.uit_bestand("data/parcours.json")
planner = RoutePlanner(kaart)
positie = {
    "laatste_punt": "D00",
    "in_edge": None,
    "op_knoop": True,
    "status": "start_bevestigd",
}
plan = planner.plan(positie, ["WILDWATER", "FREEFALL"])
for stap in plan["stappen"]:
    print(stap)