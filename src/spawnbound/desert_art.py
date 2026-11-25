from functools import lru_cache

import pygame


@lru_cache(maxsize=8)
def cactus(variant, scale=1):
    image = pygame.Surface((42, 48), pygame.SRCALPHA)
    ink, shade, mid, sun = "#1d4a3e", "#2f7c4c", "#52b05a", "#b0e872"
    if variant == "column":
        for points, width in (([(20,42),(20,9)],10), ([(19,30),(10,26),(10,18)],6),
                              ([(21,24),(30,20),(30,12)],7)):
            pygame.draw.lines(image, ink, False, points, width+2)
            pygame.draw.lines(image, shade, False, points, width)
            for x,y in points:
                pygame.draw.circle(image, shade, (x,y), width//2)
            lit = [(x-1,y-1) for x,y in points]
            pygame.draw.lines(image, mid, False, lit, max(2,width//2))
            pygame.draw.line(image, sun, lit[-1], (lit[-1][0],lit[-1][1]+4), 2)
    else:
        for rect in ((15,30,12,16),(9,23,11,14),(20,19,12,16),(6,14,10,13),(27,12,10,11)):
            x,y,w,h = rect
            pygame.draw.ellipse(image, ink, rect)
            pygame.draw.ellipse(image, mid, (x+1,y+1,w-3,h-3))
            pygame.draw.line(image, sun,(x+2,y+5),(x+4,y+3),2)
        for x,y in ((10,14),(32,12)):
            pygame.draw.ellipse(image,"#ff5c9a",(x-3,y-3,6,5))
            pygame.draw.line(image,"#ffd0e4",(x-1,y-2),(x+1,y-2))
    return pygame.transform.scale_by(image, scale)
