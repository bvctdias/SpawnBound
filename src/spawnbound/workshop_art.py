from functools import lru_cache
from math import asin, pi

import pygame


@lru_cache(maxsize=2)
def kiln(right: bool = False) -> pygame.Surface:
    image = pygame.Surface((27, 52), pygame.SRCALPHA)
    cx = 13
    profile = ((5, 6), (10, 6), (18, 9), (27, 11), (36, 12), (45, 12))
    courses = (4, 9, 15, 22, 29, 37, 45)
    bricks = ((163, 109, 94), (157, 100, 85), (159, 103, 89), (152, 96, 83))
    for (top, rt), (bottom, rb) in zip(profile, profile[1:]):
        for y in range(top, bottom):
            radius = round(rt + (rb-rt) * (y-top) / (bottom-top))
            for x in range(cx-radius, cx+radius+1):
                u = (x-cx) / radius
                belly = round(3 * (1-u*u))
                course = next(i for i in range(len(courses)-1, -1, -1) if y >= courses[i])
                angle = asin(u) / pi + .5
                joint = angle * (3 if course < 2 else 4) + .43 * (course % 2)
                color = bricks[(int(joint) + 3*course) % len(bricks)]
                shade = round(8 - 12*u - 17*u*u)
                if y == courses[course] or (joint % 1 < .095 and y > courses[course]+1):
                    shade -= 19
                if abs(x-cx) == radius:
                    shade -= 11
                image.set_at((x, y+belly), tuple(c+shade for c in color))

    def shape(color, *points):
        pygame.draw.polygon(image, color, [(26-x if right else x, y) for x, y in points])

    def rim(color, *points):
        pygame.draw.polygon(image, color, points)

    rim("#795144", (1,43),(7,46),(16,47),(25,43),(25,47),(21,49),(14,51),(9,51),(3,49),(1,47))
    rim("#a16c5b", (2,43),(8,45),(15,46),(24,43),(23,46),(17,49),(11,50),(5,48),(2,47))
    shape("#67493b", (20,46),(22,43),(24,42),(24,46),(22,48),(20,49))
    shape("#49382d", (21,46),(23,44),(24,44),(23,47),(21,48))
    shape("#6d473c", (2,44),(1,39),(1,31),(3,28),(6,26),(10,26),(13,29),(14,34),(14,42),(11,45),(7,46))
    shape("#a76858", (2,41),(1,36),(2,30),(4,27),(7,25),(10,26),(13,29),(13,42),(10,44),(8,44))
    shape("#b97b68", (2,32),(3,28),(6,26),(9,26),(10,28),(7,29),(5,29),(3,33))
    shape("#ce8d79", (7,26),(9,26),(11,28),(10,29),(8,28))
    shape("#92594e", (9,30),(11,29),(13,32),(13,42),(10,45),(8,44))
    shape("#624237", (1,34),(2,31),(4,29),(6,29),(8,31),(9,35),(9,44),(6,44),(2,42))
    shape("#3e302c", (2,33),(3,31),(5,30),(7,32),(8,36),(8,43),(5,42),(2,41))
    shape("#49342c", (6,35),(8,36),(8,43),(6,42))
    for x, y in ((3,45), (6,46), (9,48)):
        image.set_at((26-x if right else x,y), "#613e32")
    rim("#815545", (7,3),(9,1),(13,0),(17,1),(19,3),(19,8),(17,10),(10,10),(7,8))
    rim("#a8735e", (8,4),(11,6),(16,6),(18,4),(18,8),(15,10),(10,9),(8,7))
    rim("#c98f70", (7,3),(10,1),(15,1),(18,2),(19,4),(16,6),(10,6),(7,4))
    rim("#d59b78", (8,3),(10,1),(16,1),(17,2),(11,2),(9,4))
    rim("#6a4937", (10,3),(12,2),(16,2),(17,3),(16,5),(11,5),(10,4))
    pygame.draw.line(image, "#513e31", (11,3), (16,3))
    pygame.draw.line(image, "#c08b77", (11,8), (12,8))
    return image


@lru_cache(maxsize=2)
def workbench(right: bool = False) -> pygame.Surface:
    image = pygame.Surface((34, 28), pygame.SRCALPHA)

    def shape(color, *points):
        pygame.draw.polygon(image, color, points)

    for x, y in ((16,5), (3,12), (29,12), (16,18)):
        shape("#54392e", (x-1,y),(x+3,y),(x+3,y+7),(x+1,y+9),(x-2,y+8),(x-2,y+2))
        shape("#895b46", (x-1,y+2),(x+1,y+3),(x+1,y+8),(x-1,y+7))
    shape("#85523f", (1,10),(17,16),(17,22),(1,15))
    shape("#623c32", (17,16),(32,9),(32,14),(17,22))
    shape("#ac7160", (1,10),(17,1),(32,8),(32,11),(17,19),(1,12))
    shape("#c18172", (1,9),(16,0),(18,0),(33,8),(33,10),(17,18),(1,11))
    shape("#d49a88", (3,9),(16,1),(19,2),(7,9),(4,10))
    shape("#734337", (5,9),(16,3),(19,3),(29,8),(29,10),(17,16),(5,11))
    shape("#965b4c", (6,10),(16,5),(19,5),(28,9),(17,15))
    shape("#a36552", (7,10),(16,6),(22,7),(24,8),(15,13))
    pygame.draw.line(image, "#9e6251", (12,12) if right else (20,7), (22,7) if right else (26,10))
    def tool(color, *points):
        shape(color, *((33-x if right else x, y) for x,y in points))

    tool("#714737", (14,13),(16,9),(18,9),(15,14))
    tool("#d5a18e", (14,12),(15,9),(17,7),(19,8),(18,10),(16,10),(15,13))
    tool("#f9e4d9", (14,12),(15,9),(17,7),(18,8),(16,10),(15,12))
    tool("#c4897a", (18,10),(21,11),(21,12),(18,11))
    for x, y in ((16,0),(1,9),(30,9),(16,17)):
        shape("#775c61", (x-1,y+1),(x+1,y),(x+3,y+1),(x+3,y+3),(x+1,y+4),(x-1,y+3))
        shape("#b298a5", (x-1,y+1),(x+1,y),(x+3,y+1),(x+2,y+3),(x,y+3))
        pygame.draw.line(image, "#dbc3ca", (x,y+1), (x+2,y+1))
    return image
