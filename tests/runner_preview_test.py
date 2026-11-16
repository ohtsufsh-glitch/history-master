"""試遊URLのステージ選択から実際の入力・描画・リトライまでを検証する。

実行: python3 -m unittest discover -s tests -p 'runner_preview_test.py' -v
HISTORY_MASTER_ENGINE=webkit でも実行できる。実機Safariの確認は別途必要。
"""

import unittest

import runner_canvas_test as canvas
from runner_difficulty_cases import DESIGN, EXPECTED, EXPECTED_NAMES, SOLUTIONS


class RunnerPreviewTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    assert_isolated = canvas.RunnerCanvasTest.assert_isolated
    snapshot = canvas.RunnerCanvasTest.snapshot
    toggle = canvas.RunnerCanvasTest.toggle
    tap = canvas.RunnerCanvasTest.tap

    def preview_runner(self, suffix='?stagePreview=1', width=390, height=844,
                       preview_disabled=False):
        context = self.browser.new_context(viewport={'width': width, 'height': height},
            device_scale_factor=2, has_touch=True, is_mobile=True)
        self.addCleanup(context.close)
        context.add_init_script(f'({canvas.ISOLATION_GUARD})();')
        context.add_init_script(canvas.MANUAL_FRAMES)
        page = context.new_page()
        page.set_default_timeout(5000)
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        # 本番の状態公開APIを増やさず、描画時に状態を読み取るだけの計測。
        script = (canvas.ROOT / 'runner/game.js').read_text(encoding='utf-8')
        signature = 'function updateControls() {'
        self.assertIn(signature, script)
        script = script.replace(signature,
            signature + ' window.runnerPreviewState = state;', 1)
        if preview_disabled:
            flag = 'const STAGE_PREVIEW_ENABLED = true;'
            self.assertIn(flag, script)
            script = script.replace(flag, 'const STAGE_PREVIEW_ENABLED = false;', 1)
        page.route('**/runner/game.js*', lambda route: route.fulfill(
            status=200, content_type='text/javascript', body=script))
        response = page.goto(self.url + suffix)
        self.assertEqual(response.status, 200)
        page.wait_for_function('window.runnerPreviewState && runnerImages.length > 0 && '
                               'runnerImages.every(image=>image.complete)')
        self.settle(page)
        return page, errors, requests

    def settle(self, page):
        page.evaluate('runnerClock.settle()')
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.settle()')
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')

    def state(self, page):
        return page.evaluate('runnerPreviewState')

    def select_stage(self, page, stage_id):
        page.locator('#runner-stage-select').select_option(stage_id)
        self.settle(page)

    def assert_fresh(self, page, stage_id):
        state = self.state(page)
        self.assertEqual(state['stageId'], stage_id)
        self.assertEqual(state['goalDistance'], EXPECTED[stage_id]['length'])
        self.assertEqual(state['mode'], 'ready')
        self.assertEqual((state['lives'], state['invincibleRemaining']), (2, 0))
        self.assert_hearts(page, 2)
        for field in ('distance', 'elapsed', 'animationTime', 'score', 'nextSpawn',
                      'landingUntil', 'velocityY'):
            self.assertEqual(state[field], 0, field)
        self.assertEqual(state['objects'], [])
        self.assertIsNone(state['reason'])
        self.assertIsNone(state['airAction'])
        self.assertEqual(state['supportId'], 'ground')
        self.assertEqual((state['feetY'], state['jumpOriginY']), (470, 470))
        self.assertEqual(page.locator('#runner-score').inner_text(), '0')
        self.assertEqual(page.locator('#runner-progress').inner_text(), '0')
        self.assertTrue(page.locator('#runner-result').is_hidden())
        self.assertEqual(page.locator('#runner-result-title').inner_text(), '')
        self.assertEqual(page.locator('#runner-result-message').inner_text(), '')
        self.assertEqual(page.locator('#runner-result-score').inner_text(), '0')
        self.assertEqual(page.locator('#runner-result-progress').inner_text(), '0')
        self.assertEqual(self.snapshot(page)['sprite']['pose'], 'idle')
        self.assertEqual(self.snapshot(page)['pending'], 0)

    def assert_hearts(self, page, lives, initial=2):
        hud = page.locator('#runner-lives')
        self.assertEqual(hud.get_attribute('role'), 'status')
        self.assertEqual(hud.get_attribute('aria-live'), 'polite')
        self.assertEqual(hud.get_attribute('aria-label'), f'残機{initial}機中あと{lives}機')
        self.assertEqual(page.locator('#runner-hearts').get_attribute('aria-hidden'), 'true')
        hearts = ''.join(page.locator('#runner-hearts').inner_text().split())
        self.assertEqual(hearts, '♥' * lives + '♡' * (initial - lives))
        self.assertEqual(page.locator('#runner-continue, #runner-protection').count(), 0)
        self.assertNotIn('つづける', page.locator('body').inner_text())
        self.assertNotIn('シールド・無敵中', page.locator('body').inner_text())
        self.assertNotRegex(page.locator('#runner-viewport').inner_text(), r'残り\s*\d+\s*機')
        if lives:
            self.assertNotIn('ぶつかった', page.locator('#runner-viewport').inner_text())
        self.assertEqual(page.locator('.runner-hud #runner-lives').count(), 0)

    def advance_to_collision(self, page, hz=60):
        before = self.state(page)
        self.assertEqual(before['mode'], 'running')
        page.evaluate("""hz => {
          const lives=runnerPreviewState.lives;
          for(let i=0;i<60*hz && runnerPreviewState.mode==='running' &&
              runnerPreviewState.lives===lives;i++) runnerClock.advance(1000/hz,hz);
        }""", hz)
        after = self.state(page)
        self.assertEqual(after['lives'], before['lives'] - 1)
        return after

    def continue_to_gameover(self, page, hz=60):
        # 自動継続中ならボタン操作なしで次の衝突を待つ。終了済みでも使える。
        while self.state(page)['mode'] == 'running':
            self.advance_to_collision(page, hz)
        self.assertEqual((self.state(page)['mode'], self.state(page)['lives']), ('finished', 0))
        self.assert_hearts(page, 0)

    def test_normal_and_non_preview_queries_keep_legacy_course(self):
        for suffix in ('', '?stagePreview=0', '?stagePreview=true', '?other=1'):
            with self.subTest(suffix=suffix):
                page, errors, requests = self.preview_runner(suffix)
                self.assertTrue(page.locator('#runner-preview').is_hidden())
                self.assertNotIn('試遊モード・無料・記録されません', page.locator('body').inner_text())
                state = self.state(page)
                self.assertIsNone(state['stageId'])
                self.assertEqual(state['goalDistance'], 6400)
                self.assertEqual(sum(e['type'] == 'obstacle' for e in state['course']), 8)
                self.assertEqual((state['lives'], state['invincibleRemaining']), (2, 0))
                self.toggle(page)
                page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                page.evaluate('runnerClock.advance(6000,60)')
                self.assertEqual((self.state(page)['mode'], self.state(page)['lives']), ('running', 1))
                self.continue_to_gameover(page)
                self.assertEqual(page.locator('#runner-result-title').inner_text(), 'ゲームオーバー')
                self.assert_isolated(page, errors, requests)

    def test_all_six_options_show_metadata_and_select_actual_courses(self):
        page, errors, requests = self.preview_runner()
        self.assertTrue(page.locator('#runner-preview').is_visible())
        self.assertIn('試遊モード・無料・記録されません', page.locator('body').inner_text())
        select = page.locator('#runner-stage-select')
        self.assertEqual(select.input_value(), 'S01')
        self.assertFalse(select.is_disabled())
        self.assert_fresh(page, 'S01')
        options = select.locator('option')
        self.assertEqual(options.count(), 6)
        for difficulty, stage_id in enumerate(EXPECTED, 1):
            with self.subTest(stage=stage_id):
                expected = EXPECTED[stage_id]
                text = options.nth(difficulty - 1).inner_text()
                self.assertIn(stage_id, text)
                self.assertIn(EXPECTED_NAMES[stage_id], text)
                self.assertRegex(text, rf'難易度\s*{difficulty}')
                self.assertIn(f'{expected["length"] // 200}秒', text)
                self.assertRegex(text, rf'トゲ岩\s*{len(expected["rocks"])}')
                self.assertRegex(text, rf'足場\s*{len(expected["platforms"])}')
                self.assertRegex(text, rf'壁\s*{len(DESIGN[stage_id]["walls"])}')
                self.select_stage(page, stage_id)
                self.assert_fresh(page, stage_id)
                details = page.locator('#runner-stage-details').inner_text()
                self.assertIn(EXPECTED_NAMES[stage_id], details)
                self.assertIn(f'{expected["length"] // 200}秒', details)
                definition = page.evaluate("""async id =>
                    (await import('./stages.js')).STAGES.find(stage=>stage.stageId===id)
                """, stage_id)
                self.assertEqual(self.state(page)['course'], definition['course'])
        self.assert_isolated(page, errors, requests)

    def test_disabling_preview_entry_falls_back_to_legacy_course(self):
        page, errors, requests = self.preview_runner(preview_disabled=True)
        self.assertTrue(page.locator('#runner-preview').is_hidden())
        self.assertIsNone(self.state(page)['stageId'])
        self.assertEqual(self.state(page)['goalDistance'], 6400)
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(1000,120)')
        self.assertEqual(self.state(page)['mode'], 'running')
        self.assertAlmostEqual(self.state(page)['distance'], 200, delta=1e-6)
        self.assert_isolated(page, errors, requests)

    def test_finish_switch_resets_results_objects_score_and_animation(self):
        page, errors, requests = self.preview_runner()
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(10000,60)')
        self.continue_to_gameover(page)
        finished = self.state(page)
        self.assertEqual((finished['mode'], finished['reason'], finished['lives']),
                         ('finished', 'collision', 0))
        self.assertGreater(finished['score'], 0)
        self.assertGreater(finished['distance'], 0)
        self.assertGreater(finished['animationTime'], 0)
        self.assertGreater(len(finished['objects']), 0)
        self.assertFalse(page.locator('#runner-stage-select').is_disabled())
        self.select_stage(page, 'S04')
        self.assert_fresh(page, 'S04')
        self.assertEqual(page.locator('#runner-toggle').inner_text(), 'ゲーム開始')
        fresh = self.state(page)
        page.evaluate('runnerClock.advance(10000,120)')
        self.assertEqual(self.state(page), fresh)
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(1000,120)')
        self.assertAlmostEqual(self.state(page)['distance'], 200, delta=1e-6)
        self.assert_isolated(page, errors, requests)

    def test_running_and_paused_reject_changes_and_retry_keeps_stage(self):
        page, errors, requests = self.preview_runner()
        self.select_stage(page, 'S05')
        select = page.locator('#runner-stage-select')
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(6000,60)')
        self.assertTrue(select.is_disabled())
        # disabled属性だけでなく、遅延したchangeイベントも走行中は拒否する。
        select.evaluate("s=>{s.value='S02';s.dispatchEvent(new Event('change',{bubbles:true}));}")
        self.assertEqual(self.state(page)['stageId'], 'S05')
        self.assertEqual(select.input_value(), 'S05')
        self.toggle(page)
        self.assertTrue(select.is_disabled())
        paused = self.state(page)
        select.evaluate("s=>{s.value='S03';s.dispatchEvent(new Event('change',{bubbles:true}));}")
        self.assertEqual(self.state(page), paused)
        self.assertEqual(select.input_value(), 'S05')
        page.evaluate('runnerClock.advance(10000,120)')
        self.assertEqual(self.state(page), paused)
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.continue_to_gameover(page, 120)
        self.assertFalse(select.is_disabled())
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        retried = self.state(page)
        self.assertEqual((retried['stageId'], retried['mode']), ('S05', 'running'))
        self.assertEqual((retried['distance'], retried['elapsed'], retried['score'],
                          retried['animationTime'], retried['objects']), (0, 0, 0, 0, []))
        self.assertIsNone(retried['reason'])
        self.assertEqual((retried['lives'], retried['invincibleRemaining']), (2, 0))
        self.assertTrue(page.locator('#runner-result').is_hidden())
        self.assertTrue(select.is_disabled())
        self.assert_isolated(page, errors, requests)

    def test_two_lives_auto_continue_and_immunity_freeze_at_60_and_120_hz(self):
        for suffix in ('', '?stagePreview=1'):
            for hz in (60, 120):
                with self.subTest(suffix=suffix, hz=hz):
                    page, errors, requests = self.preview_runner(suffix)
                    self.assert_hearts(page, 2)
                    self.toggle(page)
                    page.evaluate('runnerClock.step(0)')
                    hit = self.advance_to_collision(page, hz)
                    self.assertEqual((hit['mode'], hit['reason'], hit['lives']), ('running', None, 1))
                    self.assertGreater(hit['score'], 0)
                    self.assertAlmostEqual(hit['invincibleRemaining'], 1, delta=1/hz + 1e-6)
                    self.assert_hearts(page, 1)
                    self.assertTrue(page.locator('#runner-result').is_hidden())
                    self.assertEqual(page.locator('#runner-toggle').inner_text(), '一時停止')
                    self.assertFalse(page.locator('#runner-jump').is_disabled())
                    self.assertGreater(self.snapshot(page)['pending'], 0)
                    self.assertIsNotNone(self.snapshot(page)['shield'])
                    if suffix:
                        select = page.locator('#runner-stage-select')
                        self.assertTrue(select.is_disabled())
                        select.evaluate("s=>{s.value='S06';s.dispatchEvent(new Event('change',{bubbles:true}));}")
                        self.assertEqual(select.input_value(), 'S01')
                    # 無敵中も実タッチでジャンプでき、距離・得点・スターを保持する。
                    self.tap(page)
                    jumped = self.state(page)
                    self.assertEqual((jumped['distance'], jumped['score'], jumped['objects']),
                                     (hit['distance'], hit['score'], hit['objects']))
                    page.evaluate('hz=>runnerClock.advance(250,hz)', hz)
                    protected = self.state(page)
                    self.assertEqual((protected['mode'], protected['lives']), ('running', 1))
                    self.assertLess(protected['feetY'], 470)
                    self.assertAlmostEqual(protected['invincibleRemaining'], hit['invincibleRemaining']-.25, delta=1e-6)
                    self.assertAlmostEqual(protected['distance'], hit['distance']+50, delta=1e-6)
                    self.assertGreaterEqual(protected['score'], hit['score'])
                    self.assert_hearts(page, 1)
                    # ユーザーによる一時停止は手動再開を維持し、無敵時間も止める。
                    self.toggle(page)
                    paused = self.state(page)
                    self.assertEqual(paused['mode'], 'paused')
                    self.assertEqual(page.evaluate('runnerClock.advance(300000)'), 0)
                    self.assertEqual(self.state(page), paused)
                    self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
                    # 回転、非表示、BFCacheのそれぞれで時間・足場・ジャンプを凍結。
                    for interruption in ('rotation', 'visibility', 'pagehide'):
                        self.toggle(page)
                        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                        if interruption == 'rotation':
                            page.set_viewport_size({'width':844,'height':390})
                            page.evaluate("window.dispatchEvent(new Event('orientationchange'))")
                        elif interruption == 'visibility':
                            page.evaluate("""() => {
                              Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
                              document.dispatchEvent(new Event('visibilitychange'));
                            }""")
                        else:
                            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
                        self.settle(page)
                        self.assertEqual(self.state(page), paused, interruption)
                        page.evaluate('runnerClock.advance(300000)')
                        self.assertEqual(self.state(page), paused, interruption)
                        if interruption == 'visibility':
                            page.evaluate("""() => {
                              delete document.hidden;
                              document.dispatchEvent(new Event('visibilitychange'));
                            }""")
                        elif interruption == 'pagehide':
                            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
                        self.settle(page)
                        self.assertEqual(self.state(page), paused, interruption)
                        self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
                    self.toggle(page)
                    page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                    self.assertEqual(self.state(page)['distance'], paused['distance'])
                    self.assertEqual(self.state(page)['invincibleRemaining'], paused['invincibleRemaining'])
                    page.evaluate('hz=>runnerClock.advance(600,hz)', hz)
                    self.assertAlmostEqual(self.state(page)['invincibleRemaining'], protected['invincibleRemaining']-.6, delta=1e-6)
                    self.assertEqual(self.state(page)['lives'], 1)
                    page.evaluate('hz=>runnerClock.advance(200,hz)', hz)
                    self.assertEqual(self.state(page)['invincibleRemaining'], 0)
                    self.assertIsNone(self.snapshot(page)['shield'])
                    self.assertEqual(self.state(page)['lives'], 1)
                    # 二重の一時停止/再開入力もプレイ状態を壊さない。
                    before = self.state(page)
                    self.toggle(page)
                    self.toggle(page)
                    self.assertEqual(self.state(page), before)
                    page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                    ended = self.advance_to_collision(page, hz)
                    self.assertEqual((ended['mode'], ended['reason'], ended['lives']), ('finished', 'collision', 0))
                    self.assertGreater(ended['distance'], hit['distance']+200)
                    self.assertGreaterEqual(ended['score'], hit['score'])
                    self.assertEqual(page.locator('#runner-result-title').inner_text(), 'ゲームオーバー')
                    self.assert_hearts(page, 0)
                    self.assertEqual(page.evaluate('runnerClock.advance(10000)'), 0)
                    self.assertEqual(self.state(page), ended)
                    self.toggle(page)
                    page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                    retried = self.state(page)
                    self.assertEqual((retried['mode'], retried['lives'], retried['invincibleRemaining']), ('running', 2, 0))
                    self.assertEqual((retried['distance'], retried['elapsed'], retried['score'], retried['objects']), (0,0,0,[]))
                    self.assertEqual(retried['stageId'], hit['stageId'])
                    self.assert_hearts(page, 2)
                    self.assert_isolated(page, errors, requests)
                    page.context.close()

    def test_clear_with_one_life_retries_same_course_with_two_lives(self):
        for suffix in ('', '?stagePreview=1'):
            with self.subTest(suffix=suffix):
                page, errors, requests = self.preview_runner(suffix)
                self.toggle(page)
                page.evaluate('runnerClock.step(0)')
                # ゴール判定の直前を作り、実際のRAFとボタンによる終了・再挑戦を検証する。
                page.evaluate("""() => {
                  runnerPreviewState.distance=runnerPreviewState.goalDistance-1;
                  runnerPreviewState.lives=1;
                }""")
                page.evaluate('runnerClock.advance(10,120)')
                cleared = self.state(page)
                self.assertEqual((cleared['mode'], cleared['reason'], cleared['lives']),
                                 ('finished', 'clear', 1))
                self.assertEqual(page.locator('#runner-result-title').inner_text(), 'クリア！')
                self.assert_hearts(page, 1)
                self.toggle(page)
                page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                retried = self.state(page)
                self.assertEqual((retried['mode'], retried['lives'], retried['invincibleRemaining']),
                                 ('running', 2, 0))
                self.assertEqual((retried['distance'], retried['score'], retried['objects']), (0, 0, []))
                self.assertEqual(retried['stageId'], cleared['stageId'])
                self.assert_hearts(page, 2)
                self.assert_isolated(page, errors, requests)

    def test_all_selected_stages_score_100_with_controls_at_60_and_120_hz(self):
        for stage_id, expected in EXPECTED.items():
            for hz in (60, 120):
                with self.subTest(stage=stage_id, hz=hz):
                    page, errors, requests = self.preview_runner()
                    self.select_stage(page, stage_id)
                    self.toggle(page)
                    page.evaluate('runnerClock.step(0)')
                    now = 0
                    for seconds in SOLUTIONS[stage_id]['perfect']:
                        target = seconds * 1000
                        page.evaluate('args=>runnerClock.advance(...args)', [target - now, hz])
                        self.tap(page)
                        now = target
                    page.evaluate('args=>runnerClock.advance(...args)',
                                  [expected['length'] / 200 * 1000 - now, hz])
                    state = self.state(page)
                    self.assertEqual((state['stageId'], state['mode'], state['reason'], state['score']),
                                     (stage_id, 'finished', 'clear', 100))
                    self.assertAlmostEqual(state['distance'], expected['length'], delta=1e-6)
                    self.assertAlmostEqual(state['elapsed'], expected['length'] / 200, delta=1e-6)
                    self.assertEqual(page.locator('#runner-result-title').inner_text(), 'クリア！')
                    self.assertEqual(page.locator('#runner-result-score').inner_text(), '100')
                    self.assertEqual(page.locator('#runner-progress').inner_text(), '100')
                    self.assert_hearts(page, 2)
                    self.assertFalse(page.locator('#runner-stage-select').is_disabled())
                    self.assertEqual(self.snapshot(page)['pending'], 0)
                    self.select_stage(page, 'S02' if stage_id == 'S01' else 'S01')
                    self.assert_fresh(page, 'S02' if stage_id == 'S01' else 'S01')
                    self.assert_isolated(page, errors, requests)
                    page.context.close()

    def test_phone_tablet_portrait_landscape_select_and_touch_controls(self):
        for width, height in ((375, 667), (390, 844), (667, 375), (844, 390),
                              (768, 1024), (1024, 768)):
            with self.subTest(width=width, height=height):
                page, errors, requests = self.preview_runner(width=width, height=height)
                select = page.locator('#runner-stage-select')
                self.assertGreaterEqual(select.bounding_box()['height'], 44)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollHeight'), height + 1)
                # 横画面でも説明・HUD・操作欄が重ならず、全ボタンが画面内に収まる。
                boxes = [page.locator(selector).bounding_box() for selector in
                         ('#runner-preview', '.runner-hud', '#runner-viewport', '.runner-footer')]
                for i, box in enumerate(boxes):
                    self.assertLessEqual(box['y'] + box['height'], height + 1)
                    for other in boxes[i + 1:]:
                        overlap_x = min(box['x'] + box['width'], other['x'] + other['width']) - max(box['x'], other['x'])
                        overlap_y = min(box['y'] + box['height'], other['y'] + other['height']) - max(box['y'], other['y'])
                        self.assertTrue(overlap_x <= 0 or overlap_y <= 0)
                self.assertTrue(page.get_by_label('ステージ', exact=False).count() > 0)
                for stage_id in EXPECTED:
                    self.select_stage(page, stage_id)
                    self.assert_fresh(page, stage_id)
                    box = select.bounding_box()
                    self.assertGreaterEqual(box['x'], 0)
                    self.assertLessEqual(box['x'] + box['width'], width)
                # 実タッチ入力で開始・ジャンプ・停止。RAFは決定的な時刻で進める。
                def touch_button(selector):
                    button = page.locator(selector)
                    button.scroll_into_view_if_needed()
                    box = button.bounding_box()
                    self.assertGreaterEqual(box['height'], 44)
                    page.touchscreen.tap(box['x'] + box['width']/2, box['y'] + box['height']/2)
                touch_button('#runner-toggle')
                page.evaluate('runnerClock.step(0)')
                touch_button('#runner-jump')
                page.evaluate('runnerClock.advance(225,60)')
                self.assertLess(self.state(page)['feetY'], 470)
                touch_button('#runner-toggle')
                self.assertEqual(self.state(page)['mode'], 'paused')
                self.assertTrue(select.is_disabled())
                self.assert_isolated(page, errors, requests)

    def test_rotation_app_switch_and_bfcache_keep_stage_and_wait_for_resume(self):
        page, errors, requests = self.preview_runner()
        self.select_stage(page, 'S06')
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(2000,120)')
        self.tap(page)
        page.evaluate('runnerClock.advance(225,120)')
        before = self.state(page)
        page.set_viewport_size({'width': 844, 'height': 390})
        page.evaluate("window.dispatchEvent(new Event('orientationchange'))")
        self.settle(page)
        before['mode'] = 'paused'
        self.assertEqual(self.state(page), before)
        page.evaluate("""() => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
        }""")
        paused = self.state(page)
        self.assertEqual(paused['mode'], 'paused')
        self.assertEqual(paused['stageId'], 'S06')
        page.evaluate('runnerClock.advance(10000,120)')
        self.assertEqual(self.state(page), paused)
        page.evaluate("""() => {
          delete document.hidden;
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
        }""")
        self.settle(page)
        self.assertEqual(self.state(page), paused)
        self.assertTrue(page.locator('#runner-stage-select').is_disabled())
        self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assertEqual(self.state(page)['distance'], paused['distance'])
        page.evaluate('runnerClock.advance(100,120)')
        self.assertAlmostEqual(self.state(page)['distance'], paused['distance'] + 20, delta=1e-6)
        self.assert_isolated(page, errors, requests)

    def test_ready_and_finished_restore_stage_selection_after_app_switch(self):
        for finished in (False, True):
            with self.subTest(finished=finished):
                page, errors, requests = self.preview_runner()
                if finished:
                    self.toggle(page)
                    page.evaluate('runnerClock.step(0)')
                    page.evaluate('runnerClock.advance(10000,60)')
                    self.continue_to_gameover(page)
                    self.assertEqual(self.state(page)['mode'], 'finished')
                before = self.state(page)
                page.evaluate("""() => {
                  Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
                  document.dispatchEvent(new Event('visibilitychange'));
                  window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
                }""")
                self.assertTrue(page.locator('#runner-stage-select').is_disabled())
                page.evaluate('runnerClock.advance(10000,60)')
                self.assertEqual(self.state(page), before)
                page.evaluate("""() => {
                  delete document.hidden;
                  document.dispatchEvent(new Event('visibilitychange'));
                  window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
                }""")
                self.settle(page)
                self.assertEqual(self.state(page), before)
                self.assertFalse(page.locator('#runner-stage-select').is_disabled())
                self.select_stage(page, 'S06')
                self.assert_fresh(page, 'S06')
                self.assert_isolated(page, errors, requests)


if __name__ == '__main__':
    unittest.main()
