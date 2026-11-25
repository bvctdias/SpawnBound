PALETTE = {
    "i": (51, 35, 48), "d": (110, 53, 67), "m": (177, 81, 91),
    "p": (238, 135, 136), "h": (255, 177, 155), "l": (255, 205, 171),
    "s": (210, 101, 108), "n": (245, 119, 119), "e": (49, 31, 36),
    "k": (77, 67, 76), "b": (141, 134, 139), "g": (193, 184, 174),
    "w": (239, 226, 197), "f": (255, 246, 219), "r": (180, 55, 57),
    "c": (241, 88, 69), "a": (238, 162, 65), "y": (255, 207, 96),
}


def stamp(body, left, top, rows):
    for y, row in enumerate(rows, top):
        for x, ink in enumerate(row, left):
            if ink != " ":
                body[x, y] = PALETTE[ink]


def pig(stride, stance):
    running = stance == "run"
    bob = -stride if running else 0
    body = {}
    for x, shift in ((-6, -stride), (3, stride)):
        stamp(body, x - shift + 3, -5 + bob, ("mm", "mm", "dm", "dd", "id"))
        stamp(body, x + shift, -4 + bob, ("hpp", "hps", "pps", "dmd", "idd"))
    stamp(body, -13, -14 + bob, (
        "       dmmmmmmd",
        "     dmhhhhhpppmd",
        "    mhhppppppppppd",
        " dpdppppppppppppppd",
        "dm dppppppppppppppd",
        " dpdpppppppppppppsd",
        "   dppppppppppppssd",
        "    mppppppppppsssd",
        "    dsspppppppsssmd",
        "     dmssssssssmmd",
        "       dmmmmmmdd",
    ))
    rooting = int(stance == "rest")
    stamp(body, -1 + rooting, -18 + bob + 2*rooting, (
        "dd       dd",
        "dpsd    dmhd",
        " mnpdhhhphsd",
        "  dphhhpppsd",
        "  dppppppppd",
        "  dpeppppepd",
        "  dpppppppps",
        "  dspphlhhhnd",
        "   msphnnnnnnd",
        "   dssnnennend",
        "    dssmnnnnmd",
        "     dmmmmmd",
    ))
    return body


def chicken(stride, stance):
    running, pecking = stance == "run", stance == "rest"
    bob = -stride if running else 0
    body = {}
    for x, shift in ((-3, -stride), (2, stride)):
        stamp(body, x + shift, -4 + bob, ("a", "y", "a", "aa", "day"))
    stamp(body, -10, -15 + bob, (
        " k",
        " kfk",
        "kgwfkk",
        " kwfwgk    kkk",
        "  kwwfwkkkwffwk",
        " kbgwwwwffffffwk",
        "  kbwwffffffwwwk",
        "   kgwwwwwwwwwwk",
        "    kgwwwwwwwggk",
        "     kggwwwwgbk",
        "      kbbggbbk",
        "        kkkk",
    ))
    wing_y = -13 if running and stride else -10
    stamp(body, -6, wing_y + bob, ("  wfffw", " gwfffwg", "  gwwgg", "   bgb"))
    stamp(body, 2 + 2*pecking, -19 + bob + 6*pecking, (
        "  c c",
        " rc cr",
        " rcccr",
        " kwffwk",
        " kfffewy",
        " gwffwyaa",
        " gwffwr",
        " gwwwcr",
        "  gwwr",
    ))
    return body
