import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import pygame
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, TreeVariant, WorldObject, TileKind
from spawnbound.domain.session import GameSession
from spawnbound.prototype_art import NativeArtPack, PrototypeArtRenderer
from spawnbound.view import camera_origin, screen_center, pick_world_point


class PrototypeArtTests(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        (ROOT/'artifacts').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts')
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        image=pygame.Surface((128,160),pygame.SRCALPHA)
        pygame.draw.rect(image,(19,211,73),(60,12,8,140))
        pygame.image.save(image,self.folder/'tree.png')
        self.manifest=self.folder/'manifest.json'
        self.manifest.write_text(json.dumps({'sprites':{'tree_pine_dark':{'file':'tree.png','canvas':[128,160],'pivot':[64,152]}}}))

    def test_native_anchor_and_alpha_mask(self):
        pack=NativeArtPack(self.manifest)
        target=pygame.Surface((200,200),pygame.SRCALPHA)
        self.assertTrue(pack.draw(target,'tree_pine_dark',(100,170)))
        self.assertEqual((19,211,73,255),tuple(target.get_at((100,60))))
        self.assertTrue(pack.contains('tree_pine_dark',0,-110))
        self.assertFalse(pack.contains('tree_pine_dark',8,-80))
        self.assertIsNone(pack.contains('missing',0,0))

    def test_zoomed_picking_uses_sprite_alpha_and_preserves_cliff_occlusion(self):
        for zoom in (1,.7):
            config=GameConfig(camera_zoom=zoom)
            session=GameSession.create(1234,config,chunk_preview_size=8)
            session.world.objects.clear()
            p=session.player.position+GridPos(2,0)
            session.world.objects[p]=WorldObject.create(p,ObjectKind.TREE,variant=TreeVariant.PINE_DARK.value)
            renderer=PrototypeArtRenderer(pygame.Surface((960,540)),config,self.manifest)
            renderer.draw_gameplay(session,debug=False)
            origin=camera_origin(session,config)
            native_origin=config.view_to_world(origin)
            x,y=screen_center(session.world.surface_position(p),native_origin,config.world_view_config)
            opaque=config.world_to_view((x,y-80))
            transparent=config.world_to_view((x+8,y-80))
            hit=pick_world_point(session,opaque,origin,config,renderer.hit_test)
            self.assertEqual((p,'object'),(hit.position,hit.kind))
            hit=pick_world_point(session,transparent,origin,config,renderer.hit_test)
            self.assertTrue(hit is None or hit.kind!='object')
            foreground=p+GridPos(1,0)
            session.world.tile_map.add(foreground,TileKind.GRASS,elevation=3)
            hidden=config.world_to_view((x,y-18))
            hit=pick_world_point(session,hidden,origin,config,renderer.hit_test)
            self.assertEqual((foreground,'tile'),(hit.position,hit.kind))


if __name__=='__main__': unittest.main()
