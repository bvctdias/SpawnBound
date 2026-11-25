from functools import lru_cache

import pygame


INGOT = """
  444444333
 43333333332
4333333333222
3222222222111
 22222222111
"""
MINERAL = """
     44
   44332
  433322 33
 33221143332
 22111233221
    3322221
     2111
"""
SEEDS = """
     43
  43 332
  32     43
     43  332
 43  332
 332
  2
"""
WARM = ("#834528", "#ba6531", "#e39449", "#ffd183")
STEEL = ("#454456", "#777b8f", "#b7bfd1", "#edf2f8")
GOLD = ("#915820", "#d98d20", "#f8bc34", "#fff195")
GLASS = ("#3e5269", "#739598", "#b9d8cd", "#f2fff1")


def drawing(name, colors, rows):
    lines = rows.strip("\n").splitlines()
    margin = (16 - max(map(len, lines))) // 2
    return name, dict(zip("1234gv", (*colors, "#397841", "#84bb56"))), "\n".join(
        "." * margin + line.replace(" ", ".") for line in lines)


CRAFT_ICONS = {
    "torch": drawing("Tocha", ("#683922", "#ab6441", "#ffa632", "#fff5a1"), """
      4
    3443
   344443
   334443
   333333
   122221
    2221
    221
    221
    221
    221
"""),
    "bed": drawing("Cama", ("#634134", "#42658a", "#68a1c1", "#ffedc3"), """
        1111
     44444411
   3344444411
  3333333221
 333332221
122222111
 111111
 11  11
"""),
    "chest": drawing("Baú", WARM, """
   44444333
  4333322222
  3322222221
  2223442221
  3322442221
  3322222211
   21111111
"""),
    "kiln": drawing("Fornalha", WARM, """
      322
     43321
    4333321
   433233221
  43333333221
  33331113321
  33211441221
  22213331121
   211111111
"""),
    "composter": drawing("Composteira", WARM, """
      444
   443gvv344
  4ggvvvgg334
  43ggvvvv322
  23443332212
  2gg34422gg2
  2ggvg22ggg2
   222g22g22
     222222
"""),
    "bench": drawing("Bancada", WARM, """
   444444
 4433333344
443333322233
332222221111
 2112221112
 21  21  12
 21  21  11
     21
"""),
    "coal": drawing("Carvão", ("#222032", "#363347", "#51495c", "#756d81"), MINERAL),
    "copper_bar": drawing("Barra de cobre", WARM, INGOT),
    "iron_ore": drawing("Minério de ferro", STEEL, MINERAL),
    "iron_bar": drawing("Barra de ferro", STEEL, INGOT),
    "gold_ore": drawing("Minério de ouro", GOLD, MINERAL),
    "gold_bar": drawing("Barra de ouro", GOLD, INGOT),
    "brick": drawing("Tijolo", ("#803e33", "#ac5d4a", "#d28465", "#efad89"), INGOT),
    "clay": drawing("Argila", ("#705760", "#a17b79", "#bc9690", "#e6c3ac"), MINERAL),
    "sand": drawing("Areia", ("#a67547", "#cca15d", "#ebcf8d", "#fff0b4"), """
     43
    4343
   343232
 433343333
33323232332
 222222221
"""),
    "glass": drawing("Vidro", GLASS, """
        44
      4434
    442  3
  443  4 3
 43   4  3
 3   4   3
 3  4   32
 3     32
 3   32
 3 32
 32
"""),
    "flask": drawing("Frasco", GLASS, """
    444
    232
    432
   43332
  4433332
  4322332
  3222221
   22111
"""),
    "jar": drawing("Pote", GLASS, """
   3333333
   2222222
  444433332
  432333232
  432333232
  432333232
  322222221
   2211111
"""),
    "carrot": drawing("Cenoura", WARM, """
        gv v
       gvgv
     4433gg
    443332
   433332
   33221
  4321
 321
 21
"""),
    "turnip": drawing("Nabo", ("#997451", "#c9a477", "#ecd5a0", "#fff0c3"), """
      v  gv
      gvgv
    4443g
   4443332
   4333322
   3333221
    22221
    21
"""),
    "pumpkin": drawing("Abóbora", WARM, """
     gvvg
     g
   434343
  433343332
 43323332332
 43323332332
 33223322221
  221221211
"""),
    "carrot_seed": drawing("Semente de cenoura", WARM, SEEDS),
    "turnip_seed": drawing("Semente de nabo", ("#66543c", "#8d7754", "#b6a173", "#e4cf9a"), """
     443
   443332
  43333332
  33332322
  33232221
   222211
    2111
"""),
    "pumpkin_seed": drawing("Semente de abóbora", ("#88734e", "#b4a37a", "#e5d4a0", "#fff1c6"), SEEDS),
}


EQUIPMENT = {
    "torch": ({"b":"#603624", "w":"#ab6741", "h":"#dc9a54", "g":"#86512d",
               "o":"#ea7c28", "f":"#ffc34b", "y":"#ffef91", "s":"#ffffd6"}, """
   y
  y
  yf y
 fsyf
 ysyfy
fysssf
fyssyf
fysyyf
offyfo
 offo
 ghhg
 bwhb
 bwhb
 bwhb
 bwhb
 bwwb
 bwwb
  bb
"""),
    "bed": ({"a":"#503027","b":"#895139","h":"#c1875a","s":"#4780aa","l":"#71a8c9",
             "d":"#315473","w":"#f5e3c3","p":"#d4ba99"}, """
                 bh
                bhhb
                bhhhhb
              wwwwbhhhhb
            wwwwwwwwbhhhhb
          llwwwwwwwwppbhhha
        llllllwwwwppssabhha
      llllllllllwwpssssdbaa
    llllllllllllllssssdbaa
  blllllllllllllssssddba
 abbslllllllllssssddba
 abhbbslllllssssddba
  abhbbbsllsssddba
   abhhbbsssddba
     abhbbddba
      aabbba
       abba
"""),
    "kiln": ({"o": "#38292c", "d": "#754334", "b": "#ad6245", "c": "#ce8053", "h": "#eca365",
              "f": "#f2a947", "y": "#ffe28a"}, """
          ooooo
         obbbddo
         ohcbbdo
         occbdoo
        ohccbbddo
       ohccbcbbddo
      ohccbbcbcbddo
     ohccbcccbbbdddo
    ohccbcccbcbbbdddo
   ohcbccbccbbbcbdddo
   occcbccbbbccbbbdddo
  ohcccbcbdddbbcbbdddo
  occbbbdooddobbbcbdddo
 ohccbbdoooooodbbbcbddo
 occbcdoooofodocbbcbddo
 occbbdooffyfodobcbdddo
 obcbdofyyyyffodbbbdddo
 obbbddooooooodbbddddo
  oddbbdddbbbddddddoo
    ooodddddddddooo
       ooooooooo
"""),
    "composter": ({"o": "#342b29", "d": "#674332", "b": "#936443", "h": "#c3905d",
                   "g": "#4e7a4b", "l": "#8bad62", "s": "#adccae", "w": "#e1dfbb"}, """
           ooo
        ooohhhoo
     ooohhssswhhoo
   oohhssgglgssshhoo
 oohhssgglglggsssshhoo
 ohsssgllgglgglggssho
 ohhhsslgllglllgshhbo
 ohgghhssglggsshhbbdo
 ohglgghhssshhbbsggdo
 ohsgllgghhhbbgggggdo
 ohsglgglghbggggslgdo
 ohhsggggghbgglgshbdo
  obhhsggghbggshhbdo
   odbhhsshbshhbddo
    oodbhhhhhhddoo
       oodbbddoo
          ooo
"""),
}


@lru_cache(maxsize=16)
def station_sprite(kind: str, scale: float = 1.) -> pygame.Surface:
    palette, drawing_rows = EQUIPMENT[kind]
    rows = drawing_rows.strip("\n").splitlines()
    size = max(map(len, rows)), len(rows)
    sprite = pygame.Surface(size, pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            if value != " ":
                sprite.set_at((x, y), palette[value])
    if scale == 1:
        return sprite
    return pygame.transform.scale(sprite, tuple(max(1, round(n * scale)) for n in size))
