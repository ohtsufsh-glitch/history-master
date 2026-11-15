"""通常4匹の選択・途中変更の拒否・タッチ表示を配信UIで検証する。

実行: python3 -m unittest discover -s tests -p 'runner_character_ui_test.py' -v
HISTORY_MASTER_ENGINE=webkit でも実行可能。Safari実機確認は別途必要。
"""

import math
import unittest

import runner_canvas_test as canvas
import runner_preview_test as preview


CHARACTERS = {
    'shiba': ('しば犬', 200, 120, .90, 2),
    'sloth': ('なまけもの', 170, 125, 1.10, 3),
    'goldfish': ('金魚', 185, 160, 1.05, 2),
    'salamander': ('オオサンショウウオ', 230, 105, .82, 2),
}


class RunnerCharacterUITest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    preview_runner = preview.RunnerPreviewTest.preview_runner
    settle = preview.RunnerPreviewTest.settle
    state = preview.RunnerPreviewTest.state
    select_stage = preview.RunnerPreviewTest.select_stage
    snapshot = canvas.RunnerCanvasTest.snapshot
    toggle = canvas.RunnerCanvasTest.toggle
    tap = canvas.RunnerCanvasTest.tap

    def assert_isolated(self, page, errors, requests):
        self.assertEqual(errors, [])
        self.assertEqual(page.evaluate('runnerStorageAccesses'), [])
        root = self.url.removesuffix('runner/')
        allowed = {root + f'assets/plush/{key}.webp' for key in CHARACTERS}
        self.assertTrue(all(url.startswith(self.url) or url in allowed for url in requests), requests)

    def select_character(self, page, character_id):
        page.locator('#runner-character-select').select_option(character_id)
        page.wait_for_function('runnerImages.every(image=>image.complete)', polling=50)
        self.settle(page)

    def assert_fresh(self, page, character_id, stage_id='S06'):
        state = self.state(page)
        self.assertEqual((state['characterId'], state['stageId'], state['mode']),
                         (character_id, stage_id, 'ready'))
        self.assertEqual(state['lives'], CHARACTERS[character_id][4])
        self.assertEqual(page.locator('#runner-lives').inner_text(), str(state['lives']))
        for field in ('distance', 'elapsed', 'animationTime', 'score', 'nextSpawn',
                      'landingUntil', 'velocityY', 'invincibleRemaining'):
            self.assertEqual(state[field], 0, field)
        self.assertEqual(state['objects'], [])
        self.assertEqual((state['feetY'], state['jumpOriginY'], state['supportId']), (470, 470, 'ground'))
        self.assertIsNone(state['reason'])
        self.assertIsNone(state['airAction'])
        self.assertEqual(page.locator('#runner-score').inner_text(), '0')
        self.assertEqual(page.locator('#runner-progress').inner_text(), '0')
        self.assertTrue(page.locator('#runner-result').is_hidden())
        self.assertTrue(page.locator('#runner-continue').is_hidden())
        self.assertTrue(page.locator('#runner-protection').is_hidden())
        self.assertEqual(page.locator('#runner-toggle').inner_text(), 'ゲーム開始')
        self.assertEqual(self.snapshot(page)['pending'], 0)

    def finish_without_jumps(self, page, lives):
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        for remaining in range(lives - 1, -1, -1):
            page.evaluate('runnerClock.advance(60000,120)')
            current = self.state(page)
            self.assertEqual(current['lives'], remaining)
            self.assertEqual(current['mode'], 'hurt' if remaining else 'finished')
            if remaining:
                self.toggle(page)
                page.evaluate('runnerClock.step(runnerClock.snapshot().now)')

    def test_four_options_image_abilities_and_default_are_preview_only(self):
        for suffix, disabled in (('', False), ('?stagePreview=0', False),
                                 ('?stagePreview=true', False), ('?stagePreview=1', True)):
            with self.subTest(suffix=suffix, disabled=disabled):
                page, errors, requests = self.preview_runner(suffix, preview_disabled=disabled)
                self.assertTrue(page.locator('#runner-character-select').is_hidden())
                self.assertEqual((self.state(page)['characterId'], self.state(page)['lives']), ('shiba', 2))
                select = page.locator('#runner-character-select')
                select.evaluate("s=>{s.value='sloth';s.dispatchEvent(new Event('change',{bubbles:true}));}")
                self.assertEqual(self.state(page)['characterId'], 'shiba')
                self.assert_isolated(page, errors, requests)
                page.context.close()
        page, errors, requests = self.preview_runner()
        select = page.get_by_label('キャラクターをえらぶ', exact=True)
        self.assertEqual(select.input_value(), 'shiba')
        self.assertEqual(select.locator('option').count(), 4)
        self.assertEqual(select.locator('option').evaluate_all('items=>items.map(item=>item.value)'),
                         list(CHARACTERS))
        self.select_stage(page, 'S06')
        for key, (name, speed, height, duration, lives) in CHARACTERS.items():
            with self.subTest(character=key):
                self.select_character(page, key)
                self.assert_fresh(page, key)
                self.assertIn(name, select.locator('option:checked').inner_text())
                details = page.locator('#runner-character-details').inner_text()
                for expected in (str(speed), str(height), str(duration), str(lives)):
                    self.assertIn(expected, details)
                image = page.locator('#runner-character-image')
                self.assertTrue(image.is_visible())
                self.assertTrue(image.get_attribute('src').endswith(f'/assets/plush/{key}.webp'))
                self.assertGreater(image.evaluate('image=>image.naturalWidth'), 0)
                self.assertIn(name, page.locator('#runner-canvas').get_attribute('aria-label'))
                self.assertIn(f'{math.ceil(8000 / speed)}秒', page.locator('#runner-stage-details').inner_text())
        self.assert_isolated(page, errors, requests)

    def test_stage_and_character_are_independent_and_finished_change_resets(self):
        page, errors, requests = self.preview_runner()
        self.select_stage(page, 'S06')
        for key, (_, _, _, _, lives) in CHARACTERS.items():
            with self.subTest(character=key):
                self.select_character(page, key)
                self.assert_fresh(page, key)
                self.select_stage(page, 'S05')
                self.assert_fresh(page, key, 'S05')
                self.select_stage(page, 'S06')
                self.finish_without_jumps(page, lives)
                ended = self.state(page)
                self.assertEqual((ended['reason'], ended['lives']), ('collision', 0))
                self.assertGreater(ended['distance'], 0)
                self.assertGreater(ended['score'], 0)
                self.assertFalse(page.locator('#runner-character-select').is_disabled())
                self.toggle(page)
                page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                retry = self.state(page)
                self.assertEqual((retry['characterId'], retry['stageId'], retry['lives'], retry['mode']),
                                 (key, 'S06', lives, 'running'))
                self.assertEqual((retry['distance'], retry['score'], retry['objects']), (0, 0, []))
                # 最終終了後のキャラ切替は同じステージを保持して完全初期化。
                for _ in range(lives):
                    page.evaluate('runnerClock.advance(60000,120)')
                    if self.state(page)['mode'] == 'hurt':
                        self.toggle(page)
                        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                next_key = 'sloth' if key != 'sloth' else 'goldfish'
                self.select_character(page, next_key)
                self.assert_fresh(page, next_key)
                self.assertEqual(page.locator('#runner-result-title').inner_text(), '')
                self.assertEqual(page.locator('#runner-result-score').inner_text(), '0')
        self.assert_isolated(page, errors, requests)

    def test_running_paused_hurt_and_hidden_reject_synthetic_changes(self):
        page, errors, requests = self.preview_runner()
        self.select_stage(page, 'S06')
        self.select_character(page, 'sloth')
        select = page.locator('#runner-character-select')

        def reject_change(mode):
            before = self.state(page)
            self.assertEqual(before['mode'], mode)
            self.assertTrue(select.is_disabled())
            select.evaluate("s=>{s.value='goldfish';s.dispatchEvent(new Event('change',{bubbles:true}));}")
            self.assertEqual(select.input_value(), 'sloth')
            self.assertEqual(self.state(page), before)

        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(1000,60)')
        reject_change('running')
        self.toggle(page)
        reject_change('paused')
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(10000,120)')
        reject_change('hurt')
        self.assertEqual(page.locator('#runner-continue-title').inner_text(), '残り2機')
        page.evaluate("""() => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
        }""")
        reject_change('hurt')
        before = self.state(page)
        page.evaluate('runnerClock.advance(300000,120)')
        self.assertEqual(self.state(page), before)
        page.evaluate("""() => {
          delete document.hidden;
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
        }""")
        self.settle(page)
        reject_change('hurt')
        self.toggle(page)
        resumed = self.state(page)
        self.assertEqual((resumed['characterId'], resumed['stageId'], resumed['lives'],
                          resumed['invincibleRemaining']), ('sloth', 'S06', 2, 1))
        for field in ('distance', 'elapsed', 'animationTime', 'score', 'objects', 'feetY',
                      'velocityY', 'supportId', 'jumpOriginY', 'airAction', 'landingUntil'):
            self.assertEqual(resumed[field], before[field], field)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(250,120)')
        shield = self.state(page)
        self.assertAlmostEqual(shield['invincibleRemaining'], .75, delta=1e-6)
        self.assertTrue(page.locator('#runner-protection').is_visible())
        page.set_viewport_size({'width': 844, 'height': 390})
        page.evaluate("window.dispatchEvent(new Event('orientationchange'))")
        self.settle(page)
        shield['mode'] = 'paused'
        self.assertEqual(self.state(page), shield)
        page.evaluate("""() => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
        }""")
        page.evaluate('runnerClock.advance(300000,120)')
        self.assertEqual(self.state(page), shield)
        page.evaluate("""() => {
          delete document.hidden;
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
        }""")
        self.settle(page)
        self.assertEqual(self.state(page), shield)
        self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
        reject_change('paused')
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assertAlmostEqual(self.state(page)['invincibleRemaining'], .75, delta=1e-6)
        page.evaluate('runnerClock.advance(10000,120)')
        self.assertEqual((self.state(page)['mode'], self.state(page)['lives']), ('hurt', 1))
        self.assertEqual(page.locator('#runner-continue-title').inner_text(), '残り1機')
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(10000,120)')
        self.assertEqual((self.state(page)['mode'], self.state(page)['lives']), ('finished', 0))
        self.assertEqual(page.locator('#runner-result-title').inner_text(), 'ゲームオーバー')
        self.assert_isolated(page, errors, requests)

    def test_portrait_landscape_four_characters_and_real_touch(self):
        for width, height in ((375, 667), (390, 844), (667, 375), (844, 390),
                              (768, 1024), (1024, 768)):
            with self.subTest(width=width, height=height):
                page, errors, requests = self.preview_runner(width=width, height=height)
                for key in CHARACTERS:
                    self.select_character(page, key)
                    self.assertEqual(self.state(page)['characterId'], key)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollHeight'), height + 1)
                    for selector in ('#runner-stage-select', '#runner-character-select',
                                     '#runner-jump', '#runner-toggle'):
                        box = page.locator(selector).bounding_box()
                        self.assertGreaterEqual(box['height'], 44)
                        self.assertGreaterEqual(box['x'], 0)
                        self.assertLessEqual(box['x'] + box['width'], width)
                        self.assertLessEqual(box['y'] + box['height'], height + 1)
                boxes = [page.locator(selector).bounding_box() for selector in
                         ('#runner-preview', '.runner-hud', '#runner-viewport', '.runner-footer')]
                for index, box in enumerate(boxes):
                    self.assertGreater(box['height'], 0)
                    for other in boxes[index + 1:]:
                        overlap_x = min(box['x'] + box['width'], other['x'] + other['width']) - max(box['x'], other['x'])
                        overlap_y = min(box['y'] + box['height'], other['y'] + other['height']) - max(box['y'], other['y'])
                        self.assertTrue(overlap_x <= 0 or overlap_y <= 0, (box, other))
                for selector in ('#runner-toggle', '#runner-jump'):
                    page.locator(selector).tap()
                    if selector == '#runner-toggle':
                        page.evaluate('runnerClock.step(0)')
                page.evaluate('runnerClock.advance(200,120)')
                self.assertEqual(self.state(page)['mode'], 'running')
                self.assertLess(self.state(page)['feetY'], 470)
                page.locator('#runner-toggle').tap()
                self.assertEqual(self.state(page)['mode'], 'paused')
                self.assertTrue(page.locator('#runner-character-select').is_disabled())
                self.assert_isolated(page, errors, requests)
                page.context.close()

    def test_broken_existing_plush_images_do_not_block_play(self):
        page, errors, requests = self.preview_runner()
        page.route('**/assets/plush/*.webp', lambda route: route.fulfill(status=404, body='missing'))
        for key in ('sloth', 'goldfish', 'salamander'):
            with self.subTest(character=key):
                self.select_character(page, key)
                self.assertEqual(self.state(page)['characterId'], key)
                self.assertEqual(page.locator('#runner-character-select').input_value(), key)
                self.assertFalse(page.locator('#runner-toggle').is_disabled())
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        page.locator('#runner-jump').dispatch_event('click')
        page.evaluate('runnerClock.advance(200,60)')
        self.assertEqual(self.state(page)['mode'], 'running')
        self.assertLess(self.state(page)['feetY'], 470)
        self.assertGreater(self.state(page)['distance'], 0)
        self.assertIsNotNone(self.snapshot(page)['character'])
        self.assert_isolated(page, errors, requests)


if __name__ == '__main__':
    unittest.main()
