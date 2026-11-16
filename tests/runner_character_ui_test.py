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
    'sloth': ('なまけもの', 170, 125, 1.10, 2),
    'goldfish': ('金魚', 185, 160, 1.05, 2),
    'salamander': ('オオサンショウウオ', 230, 105, .82, 3),
}


class RunnerCharacterUITest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    preview_runner = preview.RunnerPreviewTest.preview_runner
    settle = preview.RunnerPreviewTest.settle
    state = preview.RunnerPreviewTest.state
    assert_hearts = preview.RunnerPreviewTest.assert_hearts
    advance_to_collision = preview.RunnerPreviewTest.advance_to_collision
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
        page.locator(f'#runner-character-cards [data-choice="{character_id}"]').click()
        page.wait_for_function('runnerImages.every(image=>image.complete)', polling=50)
        self.settle(page)

    def assert_fresh(self, page, character_id, stage_id='S06'):
        state = self.state(page)
        self.assertEqual((state['characterId'], state['stageId'], state['mode']),
                         (character_id, stage_id, 'ready'))
        self.assertEqual(state['lives'], CHARACTERS[character_id][4])
        self.assert_hearts(page, state['lives'], state['initialLives'])
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
        self.assertEqual(page.locator('#runner-toggle').inner_text(), 'ゲーム開始')
        self.assertEqual(self.snapshot(page)['pending'], 0)

    def finish_without_jumps(self, page, lives, hz=120):
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        for remaining in range(lives-1,-1,-1):
            current = self.advance_to_collision(page, hz)
            self.assertEqual(current['lives'], remaining)
            self.assertEqual(current['mode'], 'running' if remaining else 'finished')
            self.assert_hearts(page, remaining, lives)
            if remaining:
                self.assertTrue(page.locator('#runner-result').is_hidden())
                self.assertEqual(page.locator('#runner-toggle').inner_text(), '一時停止')
                self.assertGreater(current['invincibleRemaining'], 1-1/hz-1e-6)

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
        select = page.locator('#runner-character-select')
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
                levels={'shiba':('中','中'),'sloth':('低','中'),'goldfish':('中','高'),'salamander':('高','低')}
                for expected in (f'走力：{levels[key][0]}', f'ジャンプ：{levels[key][1]}', '♥'*lives):
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
                page.evaluate('runnerClock.advance(60000,120)')
                next_key = 'sloth' if key != 'sloth' else 'goldfish'
                self.select_character(page, next_key)
                self.assert_fresh(page, next_key)
                self.assertEqual(page.locator('#runner-result-title').inner_text(), '')
                self.assertEqual(page.locator('#runner-result-score').inner_text(), '0')
        self.assert_isolated(page, errors, requests)

    def test_running_paused_shield_and_hidden_reject_synthetic_changes(self):
        page, errors, requests = self.preview_runner()
        self.select_stage(page, 'S06')
        self.select_character(page, 'salamander')
        select = page.locator('#runner-character-select')

        def reject_change(mode):
            before = self.state(page)
            self.assertEqual(before['mode'], mode)
            self.assertTrue(select.is_disabled())
            select.evaluate("s=>{s.value='goldfish';s.dispatchEvent(new Event('change',{bubbles:true}));}")
            self.assertEqual(select.input_value(), 'salamander')
            self.assertEqual(self.state(page), before)

        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(1000,60)')
        reject_change('running')
        self.toggle(page)
        reject_change('paused')
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        hit = self.advance_to_collision(page)
        reject_change('running')
        self.assertEqual((hit['lives'], hit['reason']), (2,None))
        self.assert_hearts(page, 2,3)
        self.assertTrue(page.locator('#runner-result').is_hidden())
        page.evaluate('runnerClock.advance(250,120)')
        shield = self.state(page)
        self.assertAlmostEqual(shield['invincibleRemaining'], hit['invincibleRemaining']-.25, delta=1e-6)
        page.set_viewport_size({'width':844,'height':390})
        page.evaluate("window.dispatchEvent(new Event('orientationchange'))")
        self.settle(page)
        shield['mode'] = 'paused'
        self.assertEqual(self.state(page), shield)
        reject_change('paused')
        page.evaluate("""() => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
        }""")
        page.evaluate('runnerClock.advance(300000,120)')
        self.assertEqual(self.state(page), shield)
        reject_change('paused')
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
        resumed = self.state(page)
        expected = dict(shield,mode='running')
        self.assertEqual(resumed, expected)
        second = self.advance_to_collision(page)
        self.assertEqual((second['mode'], second['lives']), ('running',1))
        self.assert_hearts(page, 1,3)
        reject_change('running')
        final = self.advance_to_collision(page)
        self.assertEqual((final['mode'], final['lives']), ('finished',0))
        self.assert_hearts(page, 0,3)
        self.assertEqual(page.locator('#runner-result-title').inner_text(), 'ゲームオーバー')
        self.assert_isolated(page, errors, requests)

    def test_two_and_three_life_cycles_at_60_and_120_hz(self):
        for character, (_,_,_,_,lives) in CHARACTERS.items():
            for hz in (60,120):
                with self.subTest(character=character,hz=hz):
                    page, errors, requests = self.preview_runner()
                    self.select_stage(page,'S06')
                    self.select_character(page,character)
                    self.assert_hearts(page,lives,lives)
                    self.finish_without_jumps(page,lives,hz)
                    self.assertEqual(page.locator('#runner-result-title').inner_text(),'ゲームオーバー')
                    self.toggle(page)
                    page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                    self.assert_hearts(page,lives,lives)
                    self.assert_isolated(page,errors,requests)
                    page.context.close()

    def test_portrait_landscape_four_characters_and_real_touch(self):
        for width, height in ((375, 667), (390, 844), (667, 375), (844, 390),
                              (768, 1024), (1024, 768)):
            with self.subTest(width=width, height=height):
                page, errors, requests = self.preview_runner(width=width, height=height)
                for key in CHARACTERS:
                    self.select_character(page, key)
                    self.assertEqual(self.state(page)['characterId'], key)
                    self.assert_hearts(page, CHARACTERS[key][4], CHARACTERS[key][4])
                    page.locator('#runner-stage').scroll_into_view_if_needed()
                    hud = page.locator('#runner-lives').bounding_box()
                    stage = page.locator('#runner-stage').bounding_box()
                    self.assertGreaterEqual(hud['x'], stage['x'])
                    self.assertGreaterEqual(hud['y'], stage['y'])
                    self.assertLess(hud['x']-stage['x'], 20)
                    self.assertLess(hud['y']-stage['y'], 20)
                    self.assertLess(hud['x']+hud['width'],stage['x']+stage['width'])
                    self.assertLess(hud['y']+hud['height'],stage['y']+stage['height'])
                    self.assertEqual(page.locator('#runner-lives').evaluate('e=>getComputedStyle(e).pointerEvents'),'none')
                    self.assertEqual(page.evaluate('p=>document.elementFromPoint(p.x,p.y)?.id',
                        dict(x=hud['x']+hud['width']/2,y=hud['y']+hud['height']/2)), 'runner-canvas')
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    # 現行CSSでは、小さい縦画面にCanvasとボタンを守るため縦スクロール可。
                    # 375x667はorigin/mainでも784px。横は常に画面内、操作は文書内に保つ。
                    content_height=page.evaluate('document.documentElement.scrollHeight')
                    self.assertGreater(content_height, 0)
                    for selector in ('#runner-stage-cards button:first-child', '#runner-character-cards button:first-child',
                                     '#runner-jump', '#runner-toggle'):
                        box = page.locator(selector).bounding_box()
                        self.assertGreaterEqual(box['height'], 44)
                        self.assertGreaterEqual(box['x'], 0)
                        self.assertLessEqual(box['x'] + box['width'], width)
                        self.assertLessEqual(box['y'] + box['height'], max(height,content_height) + 1)
                boxes = [page.locator(selector).bounding_box() for selector in
                         ('#runner-preview', '.runner-hud', '#runner-viewport', '.runner-footer')]
                for index, box in enumerate(boxes):
                    self.assertGreater(box['height'], 0)
                    for other in boxes[index + 1:]:
                        overlap_x = min(box['x'] + box['width'], other['x'] + other['width']) - max(box['x'], other['x'])
                        overlap_y = min(box['y'] + box['height'], other['y'] + other['height']) - max(box['y'], other['y'])
                        self.assertTrue(overlap_x <= 0 or overlap_y <= 0, (box, other))
                for selector in ('#runner-toggle', '#runner-jump'):
                    if selector == '#runner-jump':
                        # ハート上の実タップがCanvasへ届き、ジャンプできる。
                        page.locator('#runner-stage').scroll_into_view_if_needed()
                        hud = page.locator('#runner-lives').bounding_box()
                        page.touchscreen.tap(hud['x']+hud['width']/2,hud['y']+hud['height']/2)
                    else:
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
        # 静止画と新しい9コマが全て失敗した場合の名前フォールバック。
        for id in ('sloth', 'goldfish', 'salamander'):
            page.route(f'**/runner/assets/{id}/*.webp', lambda route: route.fulfill(status=404, body='missing'))
        page.evaluate("""()=>{
          window.missingArtLabels=[];
          const original=CanvasRenderingContext2D.prototype.fillText;
          CanvasRenderingContext2D.prototype.fillText=function(text,...args){missingArtLabels.push(text);return original.call(this,text,...args);};
        }""")
        for key in ('sloth', 'goldfish', 'salamander'):
            with self.subTest(character=key):
                self.select_character(page, key)
                # 選択カードで先読み済みの成功画像も、Canvas側だけ確実に失敗させる。
                page.evaluate("""id=>runnerImages.filter(image=>image.src.endsWith('/'+id+'.webp')).forEach(image=>image.src='data:image/webp,broken')""",key)
                page.wait_for_function('runnerImages.every(image=>image.complete)',polling=50)
                self.settle(page)
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
        page.locator('#runner-canvas').scroll_into_view_if_needed()
        self.settle(page)
        self.assertIsNone(self.snapshot(page)['character'])
        self.assertIn('オオサンショウウオ',page.evaluate('missingArtLabels'))
        self.assert_isolated(page, errors, requests)


if __name__ == '__main__':
    unittest.main()
