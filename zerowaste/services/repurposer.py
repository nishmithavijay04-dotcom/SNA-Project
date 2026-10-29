"""Leftover second-life ideas (static rule table, no LLM). Expired food is never suggested for people."""
import os
import pandas as pd

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "leftover_ideas.csv")

def suggest(food_type, minutes_left, refrigerated=False, path=PATH):
    ideas = pd.read_csv(path)
    ideas = ideas[ideas["food_type"] == food_type]
    if minutes_left <= 0:
        return {"safe_for_people": False, "ideas": [],
                "message": "Past its safe window: do NOT serve or donate for eating. Send to compost or biogas "
                           "(non-meat only; meat and dairy should never go to animal feed)."}
    out = []
    for r in ideas.itertuples():
        if r.safe_to_freeze == "no" and not refrigerated and minutes_left < 120:
            continue                        # short window and not chilled: skip ideas that need chilling/reheating
        out.append({"idea": r.idea, "note": r.note})
    return {"safe_for_people": True, "ideas": out, "message": ""}
