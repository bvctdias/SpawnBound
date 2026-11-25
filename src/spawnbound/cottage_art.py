from functools import lru_cache
from math import cos, pi, sin

import pygame


PIVOT = (36, 84)


@lru_cache(maxsize=1)
def cottage():
    surface = pygame.Surface((72, 96), pygame.SRCALPHA)

    def pixel(x, y):
        return round(36 + (x - 186) / 3.9), round(80 + (y - 267) / 3.9)

    def polygon(color, *points):
        pygame.draw.polygon(surface, color, [pixel(*p) for p in points])

    def beam(color, a, b, width):
        pygame.draw.line(surface, color, pixel(*a), pixel(*b), width)

    def brickwork(x0, top, x1, rise, colors):
        for row in range(2):
            start = x0
            stagger = (row * 14) % 28
            while start < x1:
                end = min(x1, start + (28 - stagger if start == x0 else 28))
                ya = top + rise * (start - x0) + 18 * row
                yb = top + rise * (end - x0) + 18 * row
                shade = colors[(start // 23 + row * 3) % len(colors)]
                polygon(shade, (start, ya), (end, yb), (end, yb+18), (start, ya+18))
                beam(colors[-1], (start, ya+3), (start, ya+14), 1)
                beam(colors[-1], (start, ya+16), (end-3, yb+16), 1)
                start = end

    polygon("#3e2824", (61, 143), (115, 91), (189, 185), (250, 89),
            (306, 142), (306, 252), (190, 314), (59, 251))
    polygon("#eeaa83", (70, 145), (115, 101), (187, 194), (187, 271), (70, 219))
    polygon("#af9073", (192, 194), (250, 100), (298, 144), (298, 218), (192, 270))
    polygon("#f7b58e", (84, 163), (168, 197), (168, 251), (151, 247),
            (139, 207), (116, 192), (85, 199))
    polygon("#c78b6c", (84, 159), (173, 193), (173, 202), (84, 166))
    polygon("#8d705d", (200, 192), (293, 151), (293, 158), (200, 201))
    polygon("#523027", (66, 146), (85, 152), (85, 222), (66, 216))
    polygon("#995940", (69, 149), (77, 152), (77, 217), (69, 214))
    polygon("#502f25", (175, 181), (197, 187), (197, 271), (175, 265))
    polygon("#93543c", (178, 186), (186, 191), (186, 267), (178, 264))
    polygon("#603b2d", (292, 148), (302, 143), (302, 219), (292, 223))
    polygon("#43261e", (67, 140), (189, 190), (302, 137), (302, 151),
            (189, 205), (67, 154))
    beam("#965742", (78, 146), (167, 183), 2)
    beam("#cc8567", (86, 146), (156, 176), 1)
    beam("#966c5a", (209, 181), (290, 145), 2)

    polygon("#5c372d", (224, 193), (262, 176), (262, 222), (224, 237))
    polygon("#995d48", (228, 195), (257, 182), (257, 219), (228, 231))
    polygon("#281d22", (232, 198), (252, 190), (252, 215), (232, 224))
    beam("#b87e66", (229, 230), (255, 219), 1)
    beam("#825346", (249, 192), (249, 212), 1)
    beam("#ad7059", (232, 195), (253, 185), 1)

    brickwork(60, 213, 190, .49, ("#c28f94", "#c5979b", "#b98890", "#b18088"))
    brickwork(190, 277, 306, -.52, ("#827588", "#897b8b", "#807182", "#766879"))
    beam("#d7a7aa", (62, 212), (187, 273), 2)
    beam("#aa9aa9", (193, 272), (302, 216), 1)

    def arch(radius, vertical, angle):
        dx = radius * cos(angle)
        return (127 + dx, 226 + .32 * dx - vertical * sin(angle))

    outer = [arch(35, 32, n*pi/16) for n in range(17)]
    polygon("#594453", (92, 267), (162, 293), *outer)
    polygon("#674e5d", (93, 219), (112, 223), (112, 271), (93, 265))
    polygon("#a87e88", (95, 219), (104, 222), (104, 268), (95, 264))
    polygon("#c5969b", (145, 231), (162, 238), (162, 289), (145, 282))
    shades = ("#d3a5aa", "#bd929d", "#c9aab5", "#dcc0c3", "#d5adb0", "#bd99a7", "#b58d97")
    for n, color in enumerate(shades):
        a, b = n*pi/7, (n+1)*pi/7
        polygon(color, arch(35,32,a), arch(35,32,(a+b)/2), arch(35,32,b),
                arch(23,21,b), arch(23,21,(a+b)/2), arch(23,21,a))
    jamb = [arch(22,20,n*pi/16) for n in range(17)]
    polygon("#543d49", (105, 267), (149, 285), *jamb)
    inner = [arch(17,14,n*pi/16) for n in range(17)]
    polygon("#322229", (110, 265), (144, 278), *inner)
    polygon("#704735", (110, 262), (145, 274), (145, 282), (105, 267))
    beam("#996c51", (109, 266), (143, 280), 1)

    def roof_plane(points, slope, offset, colors):
        mask = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        bounds = pygame.draw.polygon(mask, "white", [pixel(*p) for p in points])
        for py in range(bounds.top, bounds.bottom):
            for px in range(bounds.left, bounds.right):
                if not mask.get_at((px, py)).a:
                    continue
                x, y = 186+(px-36)*3.9, 267+(py-80)*3.9
                row, depth = divmod(y - slope*x - offset, 24)
                tile, across = divmod(x + 13*(int(row)%2), 31)
                value = colors[0 if depth < 4 else 1 if depth < 8 else 2+(int(row+tile)%3)]
                if across < 3 and depth > 13:
                    value = colors[1]
                surface.set_at((px, py), value)

    polygon("#502521", (52,147), (119,21), (126,18), (186,44),
            (246,18), (252,24), (319,146), (303,151), (252,106),
            (204,208), (186,213), (173,207), (114,107), (70,153))
    left = ("#87382f","#9b4036","#b05043","#b45346","#ae4e42")
    right = ("#783330","#873c34","#9c493f","#99463e","#a14b41")
    roof_plane([(55,145),(121,23),(186,48),(115,97)], .40, -25, left)
    roof_plane([(186,48),(246,22),(313,143),(249,94)], -.43, 131, right)
    roof_plane([(114,94),(186,56),(187,204),(174,202)], -.47, 143,
               ("#85332d","#903d34","#a34b40","#aa4e42","#a54a40"))
    roof_plane([(185,55),(250,92),(202,202),(187,207)], .46, -37,
               ("#93382e","#a64135","#b64f40","#bf5344","#b85041"))
    beam("#5e2925", (56,146), (115,96), 2)
    beam("#73352d", (115,97), (174,201), 1)
    beam("#63302a", (205,200), (250,96), 1)
    beam("#6a342c", (250,96), (313,143), 2)
    for a, b in [((124,24),(178,47)), ((204,42),(244,24)),
                 ((117,88),(167,63)), ((208,66),(252,87))]:
        beam("#c86855", a, b, 2)
        beam("#eb8770", a, b, 1)

    polygon("#514652", (164,48),(184,36),(210,47),(210,92),(189,128),(180,121),(164,93))
    polygon("#9d8397", (166,50),(187,58),(187,122),(181,116),(166,91))
    polygon("#62556e", (187,56),(206,49),(205,91),(188,122))
    for color, points in [
        ("#b79aa8",[(166,52),(174,56),(174,70),(166,66)]),
        ("#a58a9e",[(177,61),(185,63),(185,79),(176,76)]),
        ("#ad91a0",[(167,72),(177,76),(177,89),(166,86)]),
        ("#836e82",[(178,79),(185,82),(185,94),(178,91)]),
        ("#b297a6",[(172,91),(185,95),(185,111),(178,106)]),
        ("#71647e",[(190,58),(201,54),(201,69),(190,73)]),
        ("#554961",[(198,73),(206,68),(205,84),(198,88)]),
        ("#756a80",[(189,96),(198,92),(197,103),(189,115)])]:
        polygon(color, *points)
    polygon("#c1aeba", (164,46),(175,39),(193,38),(208,44),(209,51),
            (197,56),(179,57),(164,52))
    polygon("#faf0ee", (165,45),(177,38),(193,38),(206,44),(203,48),
            (191,52),(177,51),(166,48))
    polygon("#504952", (174,45),(181,42),(193,43),(199,46),(191,49),(178,48))
    beam("#dacdd4", (179,39),(193,39), 1)
    return surface
