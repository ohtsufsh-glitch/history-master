"""独立Canvas画面と段階④のゲームルール。HTTPと一時Chromiumのみを使用する。

実行: python3 -m unittest discover -s tests -p 'runner_canvas_test.py' -v
Safari実機の検証を置き換えるものではない。
"""

import functools
import http.server
import os
from pathlib import Path
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]

ISOLATION_GUARD = """() => {
  window.runnerStorageAccesses = [];
  for (const name of ['indexedDB', 'localStorage', 'sessionStorage']) {
    Object.defineProperty(window, name, {configurable: true, get() {
      runnerStorageAccesses.push(name);
      throw new Error('Runner must not access ' + name);
    }});
  }
  window.runnerFrameRequests = 0;
  const request = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = callback => {
    runnerFrameRequests++;
    return request(callback);
  };
}"""

MANUAL_FRAMES = """(() => {
  let next = 0, now = 0;
  const frames = new Map();
  const nativeFrame = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = callback => {
    const id = ++next; frames.set(id, callback); return id;
  };
  window.cancelAnimationFrame = id => frames.delete(id);
  const scene = {character: null, markers: [], feet: []};
  const proto = CanvasRenderingContext2D.prototype;
  const transform = proto.setTransform, rectangle = proto.fillRect, arc = proto.arc;
  proto.setTransform = function(...args) {
    scene.markers = [];
    scene.feet = [];
    return transform.apply(this, args);
  };
  proto.fillRect = function(x, y, width, height) {
    if (this.fillStyle === '#d5b987') {
      const point = this.getTransform().transformPoint({x, y});
      scene.markers.push(point.x * 960 / this.canvas.width);
    }
    if (this.fillStyle === '#344e47' && width === 17 && height === 12) {
      const point = this.getTransform().transformPoint({x, y});
      scene.feet.push(point.y * 540 / this.canvas.height);
    }
    return rectangle.call(this, x, y, width, height);
  };
  proto.arc = function(x, y, radius, ...rest) {
    if (radius === 36 && this.fillStyle === '#e99b45') {
      const point = this.getTransform().transformPoint({x, y});
      scene.character = {x: point.x * 960 / this.canvas.width,
                         y: point.y * 540 / this.canvas.height};
    }
    return arc.call(this, x, y, radius, ...rest);
  };
  function step(timestamp) {
    now = timestamp;
    const batch = [...frames.values()]; frames.clear();
    for (const callback of batch) callback(timestamp);
    return batch.length;
  }
  window.runnerClock = {
    step,
    // ResizeObserverの配信だけは実ブラウザへ任せ、ゲーム時間から分離する。
    settle: () => new Promise(resolve => nativeFrame(() => nativeFrame(resolve))),
    advance(milliseconds, hz=120) {
      const start = now, count = Math.max(1, Math.round(milliseconds * hz / 1000));
      let largestBatch = 0;
      for (let i=1; i<=count; i++)
        largestBatch = Math.max(largestBatch, step(start + milliseconds * i / count));
      return largestBatch;
    },
    snapshot() {
      const c = document.querySelector('#runner-canvas'), context = c.getContext('2d');
      const pixels = context.getImageData(0, 0, c.width, Math.floor(c.height * 230/540)).data;
      let background = 0;
      for (let i=0; i<pixels.length; i+=16) background = (background*31+pixels[i]) >>> 0;
      return {now, pending:frames.size, character:scene.character, feet:scene.feet,
        marker:scene.markers.find(x=>x>=0), background, image:c.toDataURL(),
        score:Number(document.querySelector('#runner-score').textContent),
        remaining:Number(document.querySelector('#runner-time').textContent)};
    }
  };
})();"""

GEOMETRY = """() => {
  const canvas = document.querySelector('#runner-canvas');
  const viewport = document.querySelector('#runner-viewport');
  const c = canvas.getBoundingClientRect(), v = viewport.getBoundingClientRect();
  const button = document.querySelector('button');
  const b = button.getBoundingClientRect();
  const transform = canvas.getContext('2d').getTransform();
  return {
    canvas: {x:c.x,y:c.y,width:c.width,height:c.height},
    viewport: {x:v.x,y:v.y,width:v.width,height:v.height},
    bitmap: {width:canvas.width,height:canvas.height},
    button: {width:b.width,height:b.height,disabled:button.disabled},
    dpr: devicePixelRatio,
    transform: {a:transform.a,d:transform.d},
    width:innerWidth,height:innerHeight,
    documentWidth:document.documentElement.scrollWidth,
    documentHeight:document.documentElement.scrollHeight,
    text:document.body.innerText
  };
}"""

HAS_DRAWING = """() => {
  const c = document.querySelector('#runner-canvas');
  if (!c || !c.width || !c.height) return false;
  const pixel = c.getContext('2d').getImageData(0, 0, 1, 1).data;
  // alpha:falseのCanvasはclearRect後も不透明な黒になる。
  return pixel[3] > 0 && pixel.slice(0, 3).some(value => value > 0);
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class RunnerCanvasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        executable = os.environ.get('HISTORY_MASTER_BROWSER') or shutil.which('chromium')
        cls.browser = cls.playwright.chromium.launch(executable_path=executable)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/runner/'

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def open_runner(self, width=390, height=844, dpr=3, setup=None):
        context = self.browser.new_context(
            viewport={'width': width, 'height': height},
            device_scale_factor=dpr, has_touch=True)
        self.addCleanup(context.close)
        context.add_init_script(f'({ISOLATION_GUARD})();')
        if setup:
            context.add_init_script(setup)
        page = context.new_page()
        page.set_default_timeout(5000)
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        response = page.goto(self.url)
        self.assertEqual(response.status, 200)
        return page, errors, requests

    def assert_isolated(self, page, errors, requests):
        self.assertEqual(errors, [])
        self.assertEqual(page.evaluate('runnerStorageAccesses'), [])
        # 親index.htmlや他機能のJS・画像を暗黙に読み込まない。
        self.assertTrue(all(url.startswith(self.url) for url in requests), requests)

    def assert_geometry(self, page):
        page.wait_for_function(HAS_DRAWING)
        actual = page.evaluate(GEOMETRY)
        c, v, bitmap = actual['canvas'], actual['viewport'], actual['bitmap']
        self.assertGreater(c['width'], 0)
        self.assertAlmostEqual(c['width'] / c['height'], 16 / 9, delta=.003)
        self.assertAlmostEqual(c['x'] + c['width'] / 2, v['x'] + v['width'] / 2, delta=1)
        self.assertAlmostEqual(c['y'] + c['height'] / 2, v['y'] + v['height'] / 2, delta=1)
        self.assertGreaterEqual(c['x'], -1)
        self.assertLessEqual(c['x'] + c['width'], actual['width'] + 1)
        self.assertLessEqual(c['width'], 961)
        self.assertLessEqual(c['height'], v['height'] + 1)
        self.assertLessEqual(actual['documentWidth'], actual['width'])
        self.assertLessEqual(actual['documentHeight'], actual['height'] + 1)
        scale = min(actual['dpr'], 2)
        self.assertAlmostEqual(bitmap['width'], c['width'] * scale, delta=1)
        self.assertAlmostEqual(bitmap['height'], c['height'] * scale, delta=1)
        self.assertLessEqual(bitmap['width'], 1920)
        self.assertLessEqual(bitmap['height'], 1080)
        self.assertAlmostEqual(actual['transform']['a'], bitmap['width'] / 960, delta=.001)
        self.assertAlmostEqual(actual['transform']['d'], bitmap['height'] / 540, delta=.001)
        self.assertFalse(actual['button']['disabled'])
        self.assertGreaterEqual(actual['button']['width'], 44)
        self.assertGreaterEqual(actual['button']['height'], 44)
        self.assertIn('ランナーゲーム', actual['text'])
        self.assertRegex(page.locator('#runner-score').inner_text(), r'^\d+$')
        self.assertGreaterEqual(int(page.locator('#runner-time').inner_text()), 0)
        self.assertLessEqual(int(page.locator('#runner-time').inner_text()), 30)
        return actual

    def test_http_static_scene_and_phone_tablet_layouts(self):
        sizes = ((375, 667, 1), (390, 844, 3), (667, 375, 2), (844, 390, 3),
                 (768, 1024, 2), (1024, 768, 2), (1024, 1366, 2), (1366, 1024, 2))
        for width, height, dpr in sizes:
            with self.subTest(width=width, height=height, dpr=dpr):
                page, errors, requests = self.open_runner(width, height, dpr)
                self.assert_geometry(page)
                self.assertEqual(page.locator('#runner-score').inner_text(), '0')
                self.assertEqual(page.locator('#runner-time').inner_text(), '30')
                # 空白や単色だけでなく、背景・走行エリア・仮キャラクターを描画する。
                colors = page.evaluate("""() => {
                  const c = document.querySelector('#runner-canvas');
                  const ctx = c.getContext('2d'), colors = new Set();
                  for (let y=0; y<c.height; y+=Math.max(1,Math.floor(c.height/40)))
                    for (let x=0; x<c.width; x+=Math.max(1,Math.floor(c.width/60)))
                      colors.add(Array.from(ctx.getImageData(x,y,1,1).data).join(','));
                  return colors.size;
                }""")
                self.assertGreaterEqual(colors, 5)
                page.locator('#runner-toggle').click()
                self.assertEqual(page.locator('#runner-toggle').inner_text(), '一時停止')
                page.locator('#runner-toggle').click()
                self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
                self.assert_isolated(page, errors, requests)

    def test_resize_repaints_and_static_page_has_no_continuous_loop(self):
        page, errors, requests = self.open_runner()
        self.assert_geometry(page)
        for width, height in ((844, 390), (390, 680), (768, 1024), (1024, 768)):
            page.set_viewport_size({'width': width, 'height': height})
            page.wait_for_timeout(80)
            self.assert_geometry(page)
        page.wait_for_timeout(120)
        frames = page.evaluate('runnerFrameRequests')
        image = page.locator('#runner-canvas').evaluate('(c) => c.toDataURL()')
        page.wait_for_timeout(160)
        self.assertEqual(page.evaluate('runnerFrameRequests'), frames)
        self.assertEqual(page.locator('#runner-canvas').evaluate('(c) => c.toDataURL()'), image)
        self.assert_isolated(page, errors, requests)

    def test_hidden_page_and_pagehide_stop_work_then_restoration_repaints(self):
        page, errors, requests = self.open_runner()
        self.assert_geometry(page)
        page.evaluate("""() => {
          Object.defineProperty(document, 'hidden', {configurable:true,get:()=>true});
          Object.defineProperty(document, 'visibilityState', {configurable:true,get:()=>'hidden'});
          document.dispatchEvent(new Event('visibilitychange'));
          const c=document.querySelector('#runner-canvas');
          c.getContext('2d').clearRect(0,0,960,540);
          window.dispatchEvent(new Event('resize'));
        }""")
        page.wait_for_timeout(80)
        self.assertFalse(page.evaluate(HAS_DRAWING))
        page.evaluate("""() => {
          delete document.hidden; delete document.visibilityState;
          document.dispatchEvent(new Event('visibilitychange'));
        }""")
        self.assert_geometry(page)
        page.evaluate("""() => {
          window.dispatchEvent(new Event('resize'));
          window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
          const c=document.querySelector('#runner-canvas');
          c.getContext('2d').clearRect(0,0,960,540);
        }""")
        page.wait_for_timeout(80)
        self.assertFalse(page.evaluate(HAS_DRAWING))
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        self.assert_geometry(page)
        self.assert_isolated(page, errors, requests)

    def test_canvas_unavailable_explains_failure_without_uncaught_error(self):
        for failure in ('return null;', "throw new Error('Canvas unavailable');"):
            with self.subTest(failure=failure):
                page, errors, requests = self.open_runner(
                    setup=f'HTMLCanvasElement.prototype.getContext = function() {{{failure}}};')
                page.locator('#runner-status').wait_for(state='visible')
                self.assertRegex(page.locator('#runner-status').inner_text(), 'Canvas|キャンバス|描画')
                self.assertTrue(page.locator('button').is_disabled())
                self.assert_isolated(page, errors, requests)

    def manual_runner(self):
        page, errors, requests = self.open_runner(setup=MANUAL_FRAMES)
        page.evaluate('runnerClock.settle()')
        page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.settle()')
        page.evaluate('runnerClock.step(0)')
        self.assert_geometry(page)
        return page, errors, requests

    def snapshot(self, page):
        return page.evaluate('runnerClock.snapshot()')

    def toggle(self, page):
        # 手動RAFではPlaywrightのボタン安定待ちに依存せず、同じclickハンドラーを呼ぶ。
        page.locator('#runner-toggle').dispatch_event('click')

    def tap(self, page, pointer_type='touch', primary=True, button=0):
        canvas = page.locator('#runner-canvas')
        canvas.dispatch_event('pointerdown', {
            'pointerType': pointer_type, 'isPrimary': primary, 'button': button,
            'pointerId': 1, 'clientX': 100, 'clientY': 100})
        canvas.dispatch_event('pointerup', {
            'pointerType': pointer_type, 'isPrimary': primary, 'button': button,
            'pointerId': 1})
        # タッチ後に互換clickが来ても、1入力を2回数えない。
        canvas.dispatch_event('click')

    def assert_marker_advance(self, before, after, distance):
        self.assertAlmostEqual((before['marker'] - after['marker']) % 108,
                               distance % 108, delta=.01)

    def assert_same_scene(self, before, after):
        # 再描画時のGPU/CPU切替による破線のAA差に依存せず、描画座標を検査する。
        for axis in ('x', 'y'):
            self.assertAlmostEqual(before['character'][axis], after['character'][axis], delta=.001)
        self.assertAlmostEqual(before['marker'], after['marker'], delta=.001)
        for first, second in zip(before['feet'], after['feet']):
            self.assertAlmostEqual(first, second, delta=.001)

    def test_running_speed_is_time_based_and_large_gaps_are_bounded(self):
        outcomes = []
        for hz in (60, 120):
            with self.subTest(hz=hz):
                page, errors, requests = self.manual_runner()
                ready = self.snapshot(page)
                self.assertEqual(ready['pending'], 0)
                self.tap(page)
                page.evaluate('runnerClock.advance(1000)')
                self.assertTrue(self.snapshot(page)['image'] == ready['image'], '開始前は静止する')
                self.toggle(page)
                page.evaluate('runnerClock.step(1000)')
                start = self.snapshot(page)
                self.assertEqual(start['pending'], 1)
                self.assertEqual(page.evaluate(f'runnerClock.advance(200,{hz})'), 1)
                self.assert_marker_advance(start, self.snapshot(page), 40)
                self.assertEqual(page.evaluate(f'runnerClock.advance(800,{hz})'), 1)
                finish = self.snapshot(page)
                self.assert_marker_advance(start, finish, 200)
                self.assertNotEqual(start['background'], finish['background'])
                self.assertEqual(finish['pending'], 1)
                self.assertAlmostEqual(finish['character']['x'], 186, delta=.001)
                outcomes.append(finish['marker'])
                # 5秒のフレーム空白でも、最大50ms（10px）だけ進める。
                page.evaluate('runnerClock.step(7000)')
                self.assert_marker_advance(finish, self.snapshot(page), 10)
                self.assertEqual(self.snapshot(page)['remaining'], finish['remaining'])
                self.assert_isolated(page, errors, requests)
        self.assertEqual(len(outcomes), 2)
        self.assertAlmostEqual(*outcomes, delta=.001)

    def test_taps_retarget_smoothly_and_pause_freezes_every_animation(self):
        page, errors, requests = self.manual_runner()
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        lower = self.snapshot(page)
        self.tap(page, primary=False)
        self.tap(page, pointer_type='mouse', button=2)
        page.evaluate('runnerClock.advance(200)')
        self.assertAlmostEqual(self.snapshot(page)['character']['y'],
                               lower['character']['y'], delta=6)
        self.tap(page)
        page.evaluate('runnerClock.advance(200)')
        upper = self.snapshot(page)
        self.assertAlmostEqual(upper['character']['y'], 326-43, delta=6)
        # マウスでも同じ動作。途中で戻しても座標が跳ばない。
        self.tap(page, pointer_type='mouse')
        page.evaluate('runnerClock.advance(80)')
        middle = self.snapshot(page)
        self.assertGreater(middle['character']['y'], upper['character']['y'] + 10)
        self.tap(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assertAlmostEqual(self.snapshot(page)['character']['y'],
                               middle['character']['y'], delta=.001)
        for _ in range(20):
            self.tap(page)
            page.evaluate('runnerClock.advance(10)')
            y = self.snapshot(page)['character']['y']
            self.assertGreaterEqual(y, 326-49)
            self.assertLessEqual(y, 470-37)
        # 移動の途中で停止し、長い停止時間とCanvasタップを無視する。
        self.toggle(page)
        self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
        paused = self.snapshot(page)
        self.assertEqual(paused['pending'], 0)
        self.tap(page)
        self.assertEqual(page.evaluate('runnerClock.advance(300000)'), 0)
        self.assertTrue(self.snapshot(page)['image'] == paused['image'], '停止中は再描画しない')
        self.assertEqual(self.snapshot(page)['remaining'], paused['remaining'])
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        resumed = self.snapshot(page)
        self.assert_same_scene(paused, resumed)
        page.evaluate('runnerClock.advance(200)')
        final = self.snapshot(page)
        self.assertAlmostEqual(final['character']['y'], 326-43, delta=6)
        self.assert_marker_advance(resumed, final, 40)
        self.assertEqual(final['pending'], 1)
        # 停止・再開を繰り返しても、再開初回はdt=0、以後50msで10px。
        for _ in range(3):
            self.toggle(page)
            stopped = self.snapshot(page)
            self.assertEqual(stopped['pending'], 0)
            page.evaluate('runnerClock.step(runnerClock.snapshot().now+10000)')
            self.toggle(page)
            page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
            continued = self.snapshot(page)
            self.assert_same_scene(stopped, continued)
            self.assertEqual(page.evaluate('runnerClock.advance(50)'), 1)
            self.assert_marker_advance(continued, self.snapshot(page), 10)
            self.assertEqual(self.snapshot(page)['pending'], 1)
        self.assert_isolated(page, errors, requests)

    def test_running_lifecycle_requires_manual_resume_and_resize_preserves_position(self):
        page, errors, requests = self.manual_runner()
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        self.tap(page)
        page.evaluate('runnerClock.advance(80)')
        before_resize = self.snapshot(page)
        page.set_viewport_size({'width': 844, 'height': 390})
        page.evaluate('runnerClock.settle()')
        page.evaluate("for(let i=0;i<10;i++)window.dispatchEvent(new Event('resize'))")
        self.assertEqual(self.snapshot(page)['pending'], 1)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assert_geometry(page)
        resized = self.snapshot(page)
        self.assertAlmostEqual(resized['character']['y'], before_resize['character']['y'], delta=.001)
        self.assertAlmostEqual(resized['marker'], before_resize['marker'], delta=.001)
        page.evaluate("""() => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new Event('resize'));
        }""")
        hidden = self.snapshot(page)
        self.assertEqual(hidden['pending'], 0)
        self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
        page.evaluate('runnerClock.step(60000)')
        self.assertTrue(self.snapshot(page)['image'] == hidden['image'], '非表示中は再描画しない')
        page.evaluate("""() => {
          delete document.hidden;
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
        }""")
        page.evaluate('runnerClock.step(60000)')
        restored = self.snapshot(page)
        self.assertEqual(restored['pending'], 0)
        self.assert_same_scene(hidden, restored)
        self.assertEqual(hidden['remaining'], restored['remaining'])
        self.toggle(page)
        page.evaluate('runnerClock.step(60000)')
        self.assert_same_scene(restored, self.snapshot(page))
        page.evaluate('runnerClock.advance(50)')
        self.assert_marker_advance(restored, self.snapshot(page), 10)
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
        left = self.snapshot(page)
        self.assertEqual(left['pending'], 0)
        page.evaluate('runnerClock.step(120000)')
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        page.evaluate('runnerClock.step(120000)')
        self.assertEqual(self.snapshot(page)['pending'], 0)
        self.assert_same_scene(left, self.snapshot(page))
        self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
        self.assert_isolated(page, errors, requests)


    def model_runner(self):
        page, errors, requests = self.manual_runner()
        # 通常のES Module APIだけを使い、実ゲームの非公開状態へテスト用hookを追加しない。
        page.evaluate("async () => { window.runnerModel = await import('./game.js'); }")
        return page, errors, requests

    def test_star_scores_once_and_offscreen_objects_are_removed(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState, updateRunner} = runnerModel;
          const state = createRunnerState([]);
          state.mode = 'running';
          state.objects = [{id:'star', type:'star', lane:1, x:186}];
          updateRunner(state, 0);
          const collected = {score:state.score, objects:state.objects.length};
          updateRunner(state, .2);
          const repeated = state.score;
          state.objects = [
            {id:'old-star',type:'star',lane:1,x:-200},
            {id:'old-obstacle',type:'obstacle',lane:1,x:-200}];
          updateRunner(state, 0);
          return {collected, repeated, objects:state.objects.length, mode:state.mode};
        }""")
        self.assertEqual(actual['collected'], {'score':10, 'objects':0})
        self.assertEqual(actual['repeated'], 10)
        self.assertEqual(actual['objects'], 0)
        self.assertEqual(actual['mode'], 'running')
        self.assert_isolated(page, errors, requests)

    def test_obstacle_collision_miss_and_priority_over_star(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState, updateRunner, remainingSeconds} = runnerModel;
          const state = createRunnerState([]);
          state.mode = 'running';
          state.objects = [{id:'upper',type:'obstacle',lane:0,x:186}];
          updateRunner(state, 0);
          const miss = state.mode;
          state.objects = [
            {id:'star',type:'star',lane:1,x:186},
            {id:'lower',type:'obstacle',lane:1,x:186}];
          state.score = 20; // 以前の更新で獲得した点は残す。
          updateRunner(state, 0);
          const stopped = JSON.stringify(state);
          updateRunner(state, 10);
          const delayed=createRunnerState([]); delayed.mode='running'; delayed.score=20;
          delayed.objects=[
            {id:'star',type:'star',lane:1,x:186},
            {id:'approaching',type:'obstacle',lane:1,x:240}];
          updateRunner(delayed,.05); // 先にスターへ触れても、同じ更新の障害物を優先。
          return {miss, mode:state.mode, reason:state.reason, score:state.score,
            remaining:remainingSeconds(state), frozen:JSON.stringify(state)===stopped,
            delayedScore:delayed.score, delayedReason:delayed.reason};
        }""")
        self.assertEqual(actual, {'miss':'running', 'mode':'finished', 'reason':'collision',
                                  'score':20, 'remaining':0, 'frozen':True,
                                  'delayedScore':20, 'delayedReason':'collision'})
        self.assert_isolated(page, errors, requests)

    def test_collision_uses_interpolated_position_during_lane_change(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState, updateRunner, switchLane} = runnerModel;
          const early = createRunnerState([]); early.mode='running';
          switchLane(early); // 目標は上だが、まだ下レーンの実座標にいる。
          early.objects=[{id:'lower',type:'obstacle',lane:1,x:186}];
          updateRunner(early, 0);
          const late = createRunnerState([]); late.mode='running';
          switchLane(late); updateRunner(late, .1);
          late.objects=[{id:'upper',type:'obstacle',lane:0,x:186}];
          updateRunner(late, 0);
          const middle={mode:late.mode,ground:late.ground,target:late.targetLane};
          updateRunner(late, .1);
          return {early:{mode:early.mode,target:early.targetLane}, middle,
            late:{mode:late.mode,reason:late.reason,ground:late.ground,
                  moving:late.transition!==null}};
        }""")
        self.assertEqual(actual['early'], {'mode':'finished', 'target':0})
        self.assertEqual(actual['middle']['mode'], 'running')
        self.assertEqual(actual['middle']['target'], 0)
        self.assertGreater(actual['middle']['ground'], 326)
        self.assertLess(actual['middle']['ground'], 470)
        self.assertEqual(actual['late']['mode'], 'finished')
        self.assertEqual(actual['late']['reason'], 'collision')
        self.assertTrue(actual['late']['moving'])
        self.assertGreater(actual['late']['ground'], 326)
        self.assert_isolated(page, errors, requests)

    def test_timer_and_spawn_progress_match_at_60_and_120_hz(self):
        page, errors, requests = self.model_runner()
        outcomes = page.evaluate("""() => {
          const {createRunnerState, updateRunner, remainingSeconds} = runnerModel;
          return [60,120].map(hz => {
            const state=createRunnerState([{at:.25,type:'star',lane:0}]);
            const ready=JSON.stringify(state); updateRunner(state, 20);
            const readyFrozen=ready===JSON.stringify(state);
            state.mode='running';
            for(let i=0;i<hz*2;i++)updateRunner(state,1/hz);
            const midway={elapsed:state.elapsed,distance:state.distance,
              x:state.objects[0].x,remaining:remainingSeconds(state)};
            state.mode='paused'; const paused=JSON.stringify(state);
            updateRunner(state,300);
            const pauseFrozen=paused===JSON.stringify(state);
            state.mode='running';
            for(let i=0;i<hz*28;i++)updateRunner(state,1/hz);
            return {readyFrozen,pauseFrozen,midway,elapsed:state.elapsed,
              mode:state.mode,reason:state.reason,remaining:remainingSeconds(state),
              distance:state.distance};
          });
        }""")
        for outcome in outcomes:
            self.assertTrue(outcome['readyFrozen'])
            self.assertTrue(outcome['pauseFrozen'])
            self.assertAlmostEqual(outcome['midway']['elapsed'], 2, delta=.000001)
            self.assertAlmostEqual(outcome['midway']['distance'], 400, delta=.000001)
            self.assertEqual(outcome['midway']['remaining'], 28)
            self.assertEqual(outcome['mode'], 'finished')
            self.assertEqual(outcome['reason'], 'clear')
            self.assertEqual(outcome['remaining'], 0)
            self.assertAlmostEqual(outcome['elapsed'], 30, delta=.000001)
            self.assertAlmostEqual(outcome['distance'], 6000, delta=.000001)
        self.assertAlmostEqual(outcomes[0]['midway']['x'], outcomes[1]['midway']['x'], delta=.000001)
        self.assert_isolated(page, errors, requests)

    def test_gameover_stops_loop_and_retry_resets_course_score_time_and_lane(self):
        page, errors, requests = self.manual_runner()
        ready = self.snapshot(page)
        self.assertEqual((ready['score'], ready['remaining']), (0, 30))
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        self.tap(page) # 上レーンへ。最初の上スター獲得後、次の上障害物に接触する。
        page.evaluate('runnerClock.advance(6500,60)')
        self.assertEqual(self.snapshot(page)['score'], 10)
        page.evaluate('runnerClock.advance(3000,60)')
        stopped = self.snapshot(page)
        self.assertEqual(stopped['remaining'], 0)
        self.assertEqual(stopped['pending'], 0)
        self.assertEqual(page.locator('#runner-toggle').inner_text(), 'もう一度')
        self.assertEqual(page.locator('#runner-result-title').inner_text(), 'ゲームオーバー')
        self.assertTrue(page.locator('#runner-result').is_visible())
        self.assertEqual(page.locator('#runner-result-score').inner_text(), '10')
        self.tap(page)
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'), 0)
        self.assertTrue(self.snapshot(page)['image'] == stopped['image'])
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        restarted = self.snapshot(page)
        self.assertEqual((restarted['score'], restarted['remaining'], restarted['pending']), (0,30,1))
        self.assert_same_scene(ready, restarted)
        self.assertTrue(page.locator('#runner-result').is_hidden())
        self.assertEqual(page.locator('#runner-toggle').inner_text(), '一時停止')
        for _ in range(4):
            self.toggle(page)
            self.assertLessEqual(self.snapshot(page)['pending'], 1)
        self.assertEqual(self.snapshot(page)['pending'], 1)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(4500,60)')
        self.assertEqual(self.snapshot(page)['score'], 10)
        self.assertEqual(self.snapshot(page)['pending'], 1)
        self.assert_isolated(page, errors, requests)

    def test_full_fixed_course_can_clear_and_finished_screen_keeps_layout(self):
        page, errors, requests = self.model_runner()
        obstacles = page.evaluate("runnerModel.COURSE.filter(item=>item.type==='obstacle')")
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        lane = 1
        for obstacle in obstacles:
            # 出現後3秒なら右端からの接近を確認でき、前の障害物は通過済み。
            target_time = (obstacle['at'] + 3) * 1000
            now = self.snapshot(page)['now']
            page.evaluate('ms=>runnerClock.advance(ms,60)', target_time-now)
            safe_lane = 1-obstacle['lane']
            if safe_lane != lane:
                self.tap(page)
                lane = safe_lane
        now = self.snapshot(page)['now']
        page.evaluate('ms=>runnerClock.advance(ms,60)', 30000-now)
        finished = self.snapshot(page)
        self.assertEqual((finished['remaining'], finished['pending']), (0,0))
        self.assertEqual(page.locator('#runner-result-title').inner_text(), 'クリア！')
        self.assertEqual(page.locator('#runner-result-score').inner_text(), str(finished['score']))
        self.assertGreater(finished['score'], 0)
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'), 0)
        self.assertTrue(self.snapshot(page)['image'] == finished['image'])
        for width, height in ((844,390),(768,1024),(1024,768)):
            page.set_viewport_size({'width':width,'height':height})
            page.evaluate('runnerClock.settle()')
            page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
            self.assert_geometry(page)
            self.assertEqual(self.snapshot(page)['pending'], 0)
            self.assertTrue(page.locator('#runner-result').is_visible())
            self.assertGreaterEqual(page.locator('#runner-toggle').bounding_box()['height'], 44)
        self.assert_isolated(page, errors, requests)


if __name__ == '__main__':
    unittest.main()
