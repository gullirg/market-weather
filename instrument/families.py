"""The canonical family maps.

Family codes order the weather vocabulary: calm, easing, up, strained,
hot. They were duplicated in three modules; this is the one copy, and
the modules that used to carry their own import from here.
"""

FAM_CODE = {"calm": 0, "easing": 1, "real_easing": 1,
            "boom": 2, "rally": 2, "steepening": 2,
            "reflation": 2, "expansion": 2, "em_bid": 2,
            "supply_glut": 3, "precautionary": 3, "inversion": 3,
            "real_tightening": 3, "em_stress": 3, "correction": 3,
            "fear_bid": 3,
            "demand_collapse": 4, "bust": 4, "stress": 4,
            "supply_squeeze": 4, "deflation_scare": 4,
            "contraction": 4, "selloff": 4, "surge": 4}

SYN_FAM = {"risk_on_calm": 0, "post_shock_glut": 3,
           "commodity_shock": 3, "inflation_shock": 4,
           "financial_stress": 4, "demand_collapse": 4}

FAM_WORD = {0: "calm", 1: "easing", 2: "up", 3: "strained", 4: "hot"}
HOT = 4
