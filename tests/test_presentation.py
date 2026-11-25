import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'dependencias')]
import pygame
from spawnbound.config import GameConfig
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.pplay_host import PPlayHost
from spawnbound.pacing import FramePacer
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame


class PresentationTests(unittest.TestCase):
    def test_inventory_blurs_the_paused_world_once_and_restores_it_on_close(self):
        pygame.font.init()
        config = GameConfig()
        session = GameSession.create(1234, config, chunk_preview_size=8)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        renderer.draw_gameplay(session, debug=False)
        sharp = pygame.image.tobytes(renderer._world_screen, "RGB")
        renderer.draw_gameplay(session, debug=False, inventory_view=(None, None, None))
        blurred = pygame.image.tobytes(renderer._world_screen, "RGB")
        self.assertNotEqual(sharp, blurred)
        with patch.object(renderer, "_draw_cached_scene", side_effect=AssertionError("paused scene redrawn")):
            renderer.draw_gameplay(session, debug=False, inventory_view=(None, 0, None))
        self.assertEqual(blurred, pygame.image.tobytes(renderer._world_screen, "RGB"))
        renderer.draw_gameplay(session, debug=False)
        self.assertEqual(sharp, pygame.image.tobytes(renderer._world_screen, "RGB"))

    def test_keys_are_named_actions_of_pplay_input_manager(self):
        from PPlay.input_manager import InputManager
        from PPlay.mouse import Mouse
        from PPlay.window import Window
        from spawnbound import pplay_host
        self.assertEqual(["I", "TAB"], InputManager._mapa_acoes["inventario"])
        self.assertTrue(set(pplay_host.ACTIONS) <= set(InputManager._mapa_acoes), "every action is PPlay's")
        host = PPlayHost.__new__(PPlayHost)
        host.window = SimpleNamespace(eventos=[], screen_to_virtual_coords=lambda x, y: (x, y))
        host.mouse = Mouse()
        asked = []

        def action_pressed(name):
            asked.append(name)
            return name in ("pausa", "barra_3")

        with patch.object(InputManager, "action_pressed", side_effect=action_pressed), \
                patch.object(Window, "get_instance", return_value=host.window), \
                patch("pygame.mouse.get_pressed", return_value=(False, False, False)), \
                patch("pygame.mouse.get_pos", return_value=(0, 0)):
            frame = host._snapshot_input()
        self.assertTrue(frame.pause_pressed)
        self.assertEqual(2, frame.hotbar_index)
        self.assertFalse(frame.inventory_pressed or frame.enter_pressed)
        self.assertIn("confirmar", asked)

    def test_input_comes_through_pplay_keyboard_and_mouse(self):
        from PPlay.keyboard import Keyboard
        from PPlay.mouse import Mouse
        from PPlay.window import Window
        Event = pygame.event.Event
        host = PPlayHost.__new__(PPlayHost)
        window = SimpleNamespace(eventos=[], screen_to_virtual_coords=lambda x, y: (x/2, y/2), keyboard=Keyboard())
        host.window, host.keyboard, host.mouse = window, window.keyboard, Mouse()

        def snapshot(events, left=False):
            window.eventos = events
            with patch.object(Window, "get_instance", return_value=window), \
                    patch("pygame.mouse.get_pressed", return_value=(left, False, False)), \
                    patch("pygame.mouse.get_pos", return_value=(90, 100)):
                return host._snapshot_input()

        frame = snapshot([Event(pygame.MOUSEWHEEL, y=2), Event(pygame.MOUSEWHEEL, y=-1),
                          Event(pygame.KEYDOWN, key=pygame.K_5), Event(pygame.KEYDOWN, key=pygame.K_6),
                          Event(pygame.KEYDOWN, key=pygame.K_TAB), Event(pygame.KEYDOWN, key=pygame.K_RETURN),
                          Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(70, 80)),
                          Event(pygame.MOUSEBUTTONUP, button=1, pos=(90, 100))])
        self.assertTrue(frame.inventory_pressed and frame.enter_pressed)
        self.assertEqual((4, 1), (frame.hotbar_index, frame.wheel_steps))
        self.assertEqual(((45, 50), (45, 50)), (frame.destination_click, frame.left_release), "a quick click")
        self.assertFalse(frame.primary_held)
        held = snapshot([Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(70, 80))], left=True)
        self.assertTrue(held.primary_held)
        self.assertIsNone(held.left_release)
        self.assertTrue(snapshot([], left=True).primary_held)
        lost = snapshot([Event(pygame.WINDOWFOCUSLOST)], left=True)
        self.assertFalse(lost.primary_held)
        self.assertIsNone(lost.left_release, "losing the focus is not a release")
        self.assertFalse(snapshot([], left=True).primary_held, "let go until pressed again")
        self.assertTrue(snapshot([Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(1, 1))], left=True).primary_held)
        self.assertEqual((45, 50), snapshot([]).left_release)

    def test_fractional_world_zoom_reduces_temporal_aliasing(self):
        pygame.font.init()
        config = GameConfig(virtual_width=140, virtual_height=140, camera_zoom=.7)
        target = pygame.Surface((140,140))
        renderer = PlaceholderRenderer(target, config)
        filtered, nearest = [], []
        for offset in (0,1):
            source = renderer._world_screen
            for y in range(source.get_height()):
                for x in range(source.get_width()):
                    v = 255*((x+y+offset)%2)
                    source.set_at((x,y),(v,v,v))
            renderer._present_world()
            filtered.append(pygame.image.tobytes(target,'RGB'))
            nearest.append(pygame.image.tobytes(pygame.transform.scale(source,target.get_size()),'RGB'))
        difference = lambda frames: sum(abs(a-b) for a,b in zip(*frames))/len(frames[0])
        self.assertLess(difference(filtered), .35*difference(nearest))

    def test_native_and_integer_presentation_keep_exact_pixels(self):
        pygame.font.init()
        renderer = PlaceholderRenderer(pygame.Surface((8,8)),GameConfig(virtual_width=8,virtual_height=8,camera_zoom=1))
        source = renderer._world_screen
        source.fill((21,90,155));source.set_at((2,3),(252,31,13))
        renderer._present_world()
        self.assertEqual(pygame.image.tobytes(source,'RGB'),pygame.image.tobytes(renderer.screen,'RGB'))
        renderer.screen = pygame.Surface((16,16))
        renderer._present_world()
        self.assertEqual((252,31,13),tuple(renderer.screen.get_at((4,6)))[:3])
        self.assertEqual((21,90,155),tuple(renderer.screen.get_at((3,6)))[:3])

    def test_window_resize_filters_only_noninteger_scale(self):
        host = PPlayHost.__new__(PPlayHost)
        host.config = GameConfig()
        for size, crisp in (((960,540),True),((1920,1080),True),((1920,1200),True),((1591,929),False),((800,450),False)):
            with self.subTest(size=size):
                host.window = SimpleNamespace(real_screen=pygame.Surface(size))
                host._configure_presentation_filter()
                self.assertEqual(crisp,host.window.pixel_art)

    def test_presentation_scale_is_a_whole_number_for_any_window(self):
        config = GameConfig()
        for size, scale in (((960, 540), 1), ((1920, 1080), 2), ((3840, 2160), 4),
                            ((2560, 1440), 3), ((1920, 1017), 2), ((800, 450), 1)):
            with self.subTest(size=size):
                actual, zoom = config.presentation_scale(size)
                ratio = min(size[0] / 960, size[1] / 540)
                self.assertEqual(scale, actual)
                self.assertAlmostEqual(scale, zoom * ratio)
        self.assertEqual(3, GameConfig(target_view_height=360).presentation_scale((1920, 1080))[0])

    def test_window_presentation_enlarges_native_pixels_without_filtering(self):
        pygame.font.init()
        for size in ((1920, 1080), (1920, 1017), (2560, 1440)):
            with self.subTest(size=size):
                config = GameConfig()
                scale, zoom = config.presentation_scale(size)
                renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
                renderer.set_camera_zoom(zoom)
                world = renderer._world_screen
                world.fill((10, 15, 20))
                for x in range(0, world.get_width(), 3):
                    pygame.draw.line(world, (220, 195, 140), (x, 0), (x, world.get_height()))
                target = pygame.Surface(size)
                renderer.present_to(target)
                ratio = min(size[0] / 960, size[1] / 540)
                left = (size[0] - int(960 * ratio)) // 2
                top = (size[1] - int(540 * ratio)) // 2
                for wx, wy in ((0, 0), (1, 5), (3, 7), (100, 200), (101, 200)):
                    expected = tuple(world.get_at((wx, wy)))[:3]
                    for dx in range(scale):
                        self.assertEqual(expected, tuple(target.get_at((left + wx * scale + dx,
                                                                         top + wy * scale + dx)))[:3])

    def test_direct_composition_retains_hud_pause_and_letterboxing(self):
        pygame.font.init()
        renderer=PlaceholderRenderer(pygame.Surface((960,540)),GameConfig())
        session=GameSession.create(1234,GameConfig(),chunk_preview_size=8)
        renderer.draw_gameplay(session,debug=False)
        reference=renderer.screen.copy()
        direct=pygame.Surface((960,540));renderer.present_to(direct)
        self.assertEqual(pygame.image.tobytes(reference,'RGB'),pygame.image.tobytes(direct,'RGB'))
        renderer.direct_presentation=True
        renderer.draw_pause();renderer.present_to(direct)
        self.assertLess(sum(direct.get_at((10,10))[:3]),sum(reference.get_at((10,10))[:3]))
        tall=pygame.Surface((960,700));renderer.present_to(tall)
        self.assertEqual((0,0,0),tuple(tall.get_at((100,0)))[:3])
        self.assertEqual(tuple(direct.get_at((100,100))),tuple(tall.get_at((100,180))))

    def test_hit_notice_preserves_the_world_on_an_rgba_display(self):
        pygame.font.init()
        config = GameConfig()
        virtual = pygame.Surface((960, 540))
        surface = pygame.Surface
        cocoa_masks = (0xff0000, 0xff00, 0xff, 0xff000000)

        def cocoa_surface(size, flags=0, depth=0, masks=None):
            # Simula o formato de pixel do Cocoa no driver de vídeo de teste.
            if not flags and not depth:
                return surface(size, 0, 32, cocoa_masks)
            if masks is not None:
                return surface(size, flags, depth, masks)
            return surface(size, flags, depth or 32)

        with patch.object(pygame, "Surface", side_effect=cocoa_surface):
            renderer = PlaceholderRenderer(virtual, config)
        renderer.direct_presentation = True
        session = GameSession.create(1234, config, chunk_preview_size=8)
        renderer.draw_gameplay(session, debug=False)
        session.warn("Energia insuficiente.")
        for size in ((960, 540), (1710, 1073), (1920, 1080)):
            with self.subTest(size=size):
                _, zoom = config.presentation_scale(size)
                renderer.set_camera_zoom(zoom)
                renderer.draw_gameplay(session, debug=False)
                world = renderer._world_screen
                world.fill((72, 95, 33, 0))
                target = pygame.Surface(size, pygame.SRCALPHA)
                renderer.present_to(target)
                self.assertTrue(renderer._ui_bounds.collidepoint(480, 270))
                self.assertEqual(0, renderer._ui_screen.get_at((480, 270)).a)
                self.assertEqual((72, 95, 33, 255), target.get_at(target.get_rect().center))

    def test_fullscreen_uses_desktop_size_and_restores_window_size(self):
        host=PPlayHost.__new__(PPlayHost)
        host._cocoa_window=None
        host.window=SimpleNamespace(real_screen=SimpleNamespace(get_size=lambda:(1100,700),get_flags=lambda:0))
        fullscreen=SimpleNamespace(get_flags=lambda:pygame.FULLSCREEN)
        with patch('pygame.display.get_desktop_sizes',return_value=[(2560,1440)]),patch('pygame.display.set_mode',return_value=fullscreen) as mode:
            host.toggle_fullscreen();mode.assert_called_with((2560,1440),pygame.FULLSCREEN)
            host.toggle_fullscreen();mode.assert_called_with((1100,700),pygame.RESIZABLE)

    def _paced_host(self, refresh, vsync):
        host = PPlayHost.__new__(PPlayHost); host.config = GameConfig()
        host.window = SimpleNamespace(update=Mock(), delta_time=Mock(side_effect=AssertionError('millisecond clock must not drive walking')))
        host.keyboard = SimpleNamespace(key_down=lambda key: False)
        host._configure_presentation_filter = Mock(); host._snapshot_input = lambda: InputFrame()
        host._pacer = FramePacer(host.config.max_fps, refresh); host._pacer.vsync = vsync
        host._last_frame_time = host._returned_at = host._refresh_checked = 100.
        host._frame_deadline = 100. + host._pacer.period
        host._present_seconds = host.elastic_seconds = 0.; host._probe_pending = False
        host._reported_hz = refresh; host._refresh_s = host._nominal_s = 1 / refresh
        host._latch = 100. + host._pacer.refreshes / refresh
        host._upload = FramePacer.UPLOAD; host._locked = False; host._measure_in = 0
        host._measure_cost = .5 / refresh
        host._last_measured = host._flip_started = None
        clock = [100.005]

        def perf_counter():
            clock[0] += 2e-5
            return clock[0]

        def sleep(seconds):
            clock[0] += seconds

        return host, clock, perf_counter, sleep

    def test_frame_delta_uses_high_resolution_clock(self):
        host, clock, perf_counter, sleep = self._paced_host(60, vsync=False)
        with patch('spawnbound.pplay_host.time.perf_counter', side_effect=perf_counter),                 patch('spawnbound.pplay_host.time.sleep', side_effect=sleep) as slept,                 patch('pygame.display.get_active', return_value=True),                 patch('pygame.display.update') as repeat:
            _, dt = host.next_frame()
        slept.assert_called_once()
        repeat.assert_not_called()
        self.assertAlmostEqual(100. + 1/60, clock[0], delta=2e-4)
        self.assertAlmostEqual(1/60, dt, delta=2e-4)
        self.assertAlmostEqual(100. + 2/60, host._frame_deadline, delta=2e-4)

    def test_one_refresh_per_frame_lets_the_display_wait(self):
        host, clock, perf_counter, sleep = self._paced_host(60, vsync=True)
        with patch('spawnbound.pplay_host.time.perf_counter', side_effect=perf_counter),                 patch('spawnbound.pplay_host.time.sleep', side_effect=sleep) as slept,                 patch('pygame.display.get_active', return_value=True),                 patch('pygame.display.update') as repeat:
            host.next_frame()
        self.assertEqual(1, host._pacer.refreshes)
        slept.assert_not_called()
        repeat.assert_not_called()
        host.window.update.assert_called_once()

    def _run_locked(self, reported, actual, frames, work=.002):
        host, clock, perf_counter, sleep = self._paced_host(reported, vsync=True)
        presents = []

        def window_update():
            host.window.frame_presenter(None)
            clock[0] += .0005
            presents.append(clock[0])

        def display_update(rect):
            clock[0] = math.ceil((presents[-1] + .0002) * actual) / actual

        host.window.update = window_update
        host.bind_presenter(lambda target: None)
        dts = []
        with patch('spawnbound.pplay_host.time.perf_counter', side_effect=perf_counter),                 patch('spawnbound.pplay_host.time.sleep', side_effect=sleep),                 patch('pygame.display.get_active', return_value=True),                 patch('pygame.display.update', side_effect=display_update):
            for _ in range(frames):
                clock[0] += work
                dts.append(host.next_frame()[1])
        taken = [math.ceil((t + .0002) * actual) for t in presents]
        return host, presents, taken, dts

    def test_phase_lock_shows_every_frame_for_the_same_whole_refreshes(self):
        for refresh in (120, 144, 165, 240, 300, 360, 500):
            with self.subTest(refresh=refresh):
                host, presents, taken, dts = self._run_locked(refresh, refresh, 60)
                k = host._pacer.refreshes
                self.assertGreater(k, 1)
                self.assertEqual([k] * 59, [b - a for a, b in zip(taken, taken[1:])])
                for t in presents[5:]:
                    self.assertLess(abs((t * refresh) % 1 - .5), .2)
                for dt in dts[5:]:
                    self.assertAlmostEqual(k / refresh, dt, delta=.0003)

    def test_phase_lock_follows_a_display_slightly_off_its_reported_rate(self):
        for reported, actual in ((144, 143.86), (300, 299.0), (240, 240.6)):
            with self.subTest(reported=reported, actual=actual):
                host, presents, taken, dts = self._run_locked(reported, actual, 1500, work=.0065)
                k = host._pacer.refreshes
                self.assertGreater(k, 1)
                steps = [b - a for a, b in zip(taken, taken[1:])]
                self.assertEqual([k] * 1000, steps[-1000:])
                self.assertLess(abs(host._refresh_s * actual - 1), abs(reported / actual - 1))

    def test_phase_lock_keeps_an_even_cadence_on_adaptive_refresh_displays(self):
        host, clock, perf_counter, sleep = self._paced_host(300, vsync=True)
        presents = []

        def window_update():
            host.window.frame_presenter(None)
            clock[0] += .0005
            presents.append(clock[0])

        def display_update(rect):
            clock[0] = presents[-1] + .00085

        host.window.update = window_update
        host.bind_presenter(lambda target: None)
        with patch('spawnbound.pplay_host.time.perf_counter', side_effect=perf_counter),                 patch('spawnbound.pplay_host.time.sleep', side_effect=sleep),                 patch('pygame.display.get_active', return_value=True),                 patch('pygame.display.update', side_effect=display_update):
            for _ in range(3000):
                clock[0] += .0065
                host.next_frame()
        gaps = [b - a for a, b in zip(presents, presents[1:])][-1000:]
        period = host._pacer.period
        self.assertLess(max(gaps) - min(gaps), .0005)
        self.assertLess(abs(sum(gaps) / len(gaps) / period - 1), .03)

    def test_refresh_estimate_ignores_late_stamps_and_prefers_exact_modes(self):
        on_time = [n / 300 for n in range(20)]
        late = list(on_time); late[7] += .002; late[15] += .003
        self.assertEqual(1 / 300, PPlayHost._estimate_refresh(late, 300))
        fractional = [n / 119.88 for n in range(20)]
        self.assertAlmostEqual(1 / 119.88, PPlayHost._estimate_refresh(fractional, 119), places=7)
        self.assertEqual(1 / 60, PPlayHost._estimate_refresh([0.] * 20, 60))

    def test_minimised_window_waits_on_the_timer(self):
        host, clock, perf_counter, sleep = self._paced_host(144, vsync=True)
        with patch('spawnbound.pplay_host.time.perf_counter', side_effect=perf_counter), \
                patch('spawnbound.pplay_host.time.sleep', side_effect=sleep) as slept, \
                patch('pygame.display.get_active', return_value=False), \
                patch('pygame.display.update') as repeat:
            host.next_frame()
        slept.assert_called_once()
        repeat.assert_not_called()

    def test_prefetch_uses_half_the_measured_idle_time(self):
        renderer = PlaceholderRenderer.__new__(PlaceholderRenderer)
        for spare, budget in ((None, .004), (.0004, .0005), (.003, .0015), (.02, .004)):
            with self.subTest(spare=spare):
                renderer.frame_spare = spare
                self.assertAlmostEqual(budget, renderer.prefetch_budget)


if __name__ == '__main__': unittest.main()
