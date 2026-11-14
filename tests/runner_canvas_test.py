"""独立Canvas画面・距離ゴール・しば犬描画。HTTPと一時Chromiumのみを使用する。

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
  window.runnerImages = [];
  const OriginalImage = window.Image;
  window.Image = function(...args) {
    const image = new OriginalImage(...args);
    runnerImages.push(image);
    return image;
  };
  window.Image.prototype = OriginalImage.prototype;
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
  const scene = {character: null, markers: [], feet: [], sprite:null, goal:null};
  const proto = CanvasRenderingContext2D.prototype;
  const transform = proto.setTransform, rectangle = proto.fillRect, arc = proto.arc;
  const drawImage = proto.drawImage, fillText = proto.fillText;
  proto.setTransform = function(...args) {
    scene.markers = [];
    scene.feet = [];
    scene.character = null;
    scene.sprite = null;
    scene.goal = null;
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
  proto.drawImage = function(image, ...args) {
    if (image.src?.endsWith('/assets/plush/shiba.webp') && args.length === 4) {
      const [x,y,width,height] = args;
      const point=this.getTransform().transformPoint({x:x+width/2,y:y+height*465/512-43});
      scene.character={x:point.x*960/this.canvas.width,y:point.y*540/this.canvas.height};
      scene.sprite={x,y,width,height,src:image.src,
        naturalWidth:image.naturalWidth,naturalHeight:image.naturalHeight};
    }
    return drawImage.call(this,image,...args);
  };
  proto.fillText = function(text, x, y, ...args) {
    if (text === 'GOAL') scene.goal={x,y};
    return fillText.call(this,text,x,y,...args);
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
        sprite:scene.sprite,goal:scene.goal,
        marker:scene.markers.find(x=>x>=0), background, image:c.toDataURL(),
        score:Number(document.querySelector('#runner-score').textContent),
        progress:Number(document.querySelector('#runner-progress').textContent)};
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

    def open_runner(self, width=390, height=844, dpr=3, setup=None, broken_image=False):
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
        if broken_image:
            page.route('**/assets/plush/shiba.webp', lambda route: route.fulfill(status=404, body='missing'))
        response = page.goto(self.url)
        self.assertEqual(response.status, 200)
        return page, errors, requests

    def assert_isolated(self, page, errors, requests):
        self.assertEqual(errors, [])
        self.assertEqual(page.evaluate('runnerStorageAccesses'), [])
        # 再利用するしば犬画像1点だけを許可し、親アプリのJSやページは読まない。
        shiba = self.url.removesuffix('runner/') + 'assets/plush/shiba.webp'
        self.assertTrue(all(url.startswith(self.url) or url == shiba for url in requests), requests)

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
        self.assertGreaterEqual(int(page.locator('#runner-progress').inner_text()), 0)
        self.assertLessEqual(int(page.locator('#runner-progress').inner_text()), 100)
        self.assertEqual(page.locator('#runner-time').count(), 0)
        return actual

    def test_http_static_scene_and_phone_tablet_layouts(self):
        sizes = ((375, 667, 1), (390, 844, 3), (667, 375, 2), (844, 390, 3),
                 (768, 1024, 2), (1024, 768, 2), (1024, 1366, 2), (1366, 1024, 2))
        for width, height, dpr in sizes:
            with self.subTest(width=width, height=height, dpr=dpr):
                page, errors, requests = self.open_runner(width, height, dpr)
                self.assert_geometry(page)
                self.assertEqual(page.locator('#runner-score').inner_text(), '0')
                self.assertEqual(page.locator('#runner-progress').inner_text(), '0')
                # 空白や単色だけでなく、背景・地面・キャラクターを描画する。
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

    def manual_runner(self, broken_image=False):
        page, errors, requests = self.open_runner(setup=MANUAL_FRAMES, broken_image=broken_image)
        page.wait_for_function('runnerImages.length > 0 && runnerImages.every(image=>image.complete)')
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
        # 画像の再描画でも実際の描画座標が保持されることを検査する。
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
                self.assertEqual(self.snapshot(page)['progress'], finish['progress'])
                self.assert_isolated(page, errors, requests)
        self.assertEqual(len(outcomes), 2)
        self.assertAlmostEqual(*outcomes, delta=.001)

    def test_tap_jumps_once_and_pause_freezes_every_animation(self):
        page, errors, requests = self.manual_runner()
        self.toggle(page)
        page.evaluate('runnerClock.step(0)')
        grounded = self.snapshot(page)
        self.tap(page, primary=False)
        self.tap(page, pointer_type='mouse', button=2)
        page.evaluate('runnerClock.advance(200)')
        self.assertAlmostEqual(self.snapshot(page)['character']['y'],
                               grounded['character']['y'], delta=6)
        self.tap(page)
        page.evaluate('runnerClock.advance(225)')
        rising = self.snapshot(page)
        self.assertAlmostEqual(rising['character']['y'], 470-43-90, delta=.01)
        # touch互換clickや連打・長押しを追加のジャンプとして扱わない。
        for _ in range(20):
            self.tap(page)
        page.evaluate('runnerClock.advance(225)')
        apex = self.snapshot(page)
        self.assertAlmostEqual(apex['character']['y'], 470-43-120, delta=.01)
        self.toggle(page)
        self.assertEqual(page.locator('#runner-toggle').inner_text(), '再開')
        paused = self.snapshot(page)
        self.assertEqual(paused['pending'], 0)
        self.tap(page)
        self.assertEqual(page.evaluate('runnerClock.advance(300000)'), 0)
        self.assertTrue(self.snapshot(page)['image'] == paused['image'], '空中停止中は再描画しない')
        self.assertEqual(self.snapshot(page)['progress'], paused['progress'])
        self.toggle(page)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        resumed = self.snapshot(page)
        self.assert_same_scene(paused, resumed)
        page.evaluate('runnerClock.advance(450)')
        landed = self.snapshot(page)
        self.assertAlmostEqual(landed['character']['y'], 470-43, delta=6)
        self.assert_marker_advance(resumed, landed, 90)
        # 着地後はマウスでも再ジャンプできる。
        self.tap(page, pointer_type='mouse')
        page.evaluate('runnerClock.advance(225)')
        self.assertAlmostEqual(self.snapshot(page)['character']['y'], 470-43-90, delta=.01)
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
        self.assertEqual(hidden['progress'], restored['progress'])
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

    def test_jump_has_fixed_height_parabolic_motion_and_exact_landing(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState, updateRunner, startJump, GROUND_Y, JUMP} = runnerModel;
          const state=createRunnerState([]); state.mode='running';
          updateRunner(state,1);
          const idle={offset:state.jumpOffset,ground:state.ground,jumping:state.jumping};
          startJump(state); updateRunner(state,.225);
          const rising={offset:state.jumpOffset,velocity:state.jumpVelocity};
          const airborne=JSON.stringify(state);
          for(let i=0;i<20;i++)startJump(state);
          const repeatedIgnored=airborne===JSON.stringify(state);
          updateRunner(state,.225);
          const apex={offset:state.jumpOffset,velocity:state.jumpVelocity};
          updateRunner(state,.225);
          const descending={offset:state.jumpOffset,velocity:state.jumpVelocity};
          updateRunner(state,.225);
          const landed={offset:state.jumpOffset,velocity:state.jumpVelocity,
            ground:state.ground,jumping:state.jumping};
          updateRunner(state,1);
          const grounded=state.jumpOffset===0&&state.ground===GROUND_Y;
          startJump(state); updateRunner(state,.45);
          return {idle,rising,repeatedIgnored,apex,descending,landed,grounded,
            secondApex:state.jumpOffset,ground:GROUND_Y,config:JUMP};
        }""")
        self.assertEqual(actual['idle'], {'offset':0,'ground':actual['ground'],'jumping':False})
        self.assertAlmostEqual(actual['rising']['offset'], 90, delta=.000001)
        self.assertGreater(actual['rising']['velocity'], 0)
        self.assertTrue(actual['repeatedIgnored'])
        self.assertAlmostEqual(actual['apex']['offset'], 120, delta=.000001)
        self.assertAlmostEqual(actual['apex']['velocity'], 0, delta=.000001)
        self.assertAlmostEqual(actual['descending']['offset'], 90, delta=.000001)
        self.assertLess(actual['descending']['velocity'], 0)
        self.assertEqual(actual['landed'], {'offset':0,'velocity':0,
                                           'ground':actual['ground'],'jumping':False})
        self.assertTrue(actual['grounded'])
        self.assertAlmostEqual(actual['secondApex'], 120, delta=.000001)
        self.assert_isolated(page, errors, requests)

    def test_star_scores_once_on_ground_and_in_air_and_offscreen_objects_are_removed(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState, updateRunner, startJump} = runnerModel;
          const state=createRunnerState([]); state.mode='running';
          state.objects=[{id:'ground-star',type:'star',height:0,x:186}];
          updateRunner(state,0);
          const collected={score:state.score,objects:state.objects.length};
          updateRunner(state,.2);
          const repeated=state.score;
          startJump(state); updateRunner(state,.45);
          state.objects=[{id:'air-star',type:'star',height:120,x:186}];
          updateRunner(state,0);
          const airScore=state.score;
          updateRunner(state,.1);
          const airRepeated=state.score;
          state.objects=[{id:'old-star',type:'star',height:0,x:-200},
                         {id:'old-obstacle',type:'obstacle',x:-200}];
          updateRunner(state,0);
          return {collected,repeated,airScore,airRepeated,objects:state.objects.length,mode:state.mode};
        }""")
        self.assertEqual(actual['collected'], {'score':10,'objects':0})
        self.assertEqual(actual['repeated'], 10)
        self.assertEqual((actual['airScore'], actual['airRepeated']), (20,20))
        self.assertEqual(actual['objects'], 0)
        self.assertEqual(actual['mode'], 'running')
        self.assert_isolated(page, errors, requests)

    def test_obstacle_collision_miss_and_priority_over_star(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState,updateRunner,progressPercent}=runnerModel;
          const state=createRunnerState([]); state.mode='running';
          state.objects=[{id:'distant',type:'obstacle',x:500}];
          updateRunner(state,0); const miss=state.mode;
          state.objects=[{id:'star',type:'star',height:0,x:186},
                         {id:'box',type:'obstacle',x:186}];
          state.score=20; updateRunner(state,0);
          const stopped=JSON.stringify(state); updateRunner(state,10);
          const delayed=createRunnerState([]); delayed.mode='running'; delayed.score=20;
          delayed.objects=[{id:'star',type:'star',height:0,x:186},
                           {id:'approaching',type:'obstacle',x:240}];
          updateRunner(delayed,.05);
          return {miss,mode:state.mode,reason:state.reason,score:state.score,
            progress:progressPercent(state),frozen:JSON.stringify(state)===stopped,
            delayedScore:delayed.score,delayedReason:delayed.reason};
        }""")
        self.assertEqual(actual, {'miss':'running','mode':'finished','reason':'collision',
                                  'score':20,'progress':0,'frozen':True,
                                  'delayedScore':20,'delayedReason':'collision'})
        self.assert_isolated(page, errors, requests)

    def test_box_collision_uses_actual_height_and_a_jump_clears_the_box(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState,updateRunner,startJump}=runnerModel;
          const early=createRunnerState([]); early.mode='running'; startJump(early);
          early.objects=[{id:'box',type:'obstacle',x:186}]; updateRunner(early,0);
          const over=createRunnerState([]); over.mode='running'; startJump(over);
          updateRunner(over,.45);
          over.objects=[{id:'box',type:'obstacle',x:186}]; updateRunner(over,0);
          const apex={mode:over.mode,offset:over.jumpOffset};
          updateRunner(over,.45);
          const passed={mode:over.mode,offset:over.jumpOffset,jumping:over.jumping};
          const descending=createRunnerState([]); descending.mode='running'; startJump(descending);
          updateRunner(descending,.83);
          descending.objects=[{id:'box',type:'obstacle',x:186}]; updateRunner(descending,0);
          return {early:early.mode,apex,passed,descending:{mode:descending.mode,
            offset:descending.jumpOffset,jumping:descending.jumping}};
        }""")
        self.assertEqual(actual['early'], 'finished')
        self.assertEqual(actual['apex']['mode'], 'running')
        self.assertAlmostEqual(actual['apex']['offset'], 120, delta=.000001)
        self.assertEqual(actual['passed'], {'mode':'running','offset':0,'jumping':False})
        self.assertEqual(actual['descending']['mode'], 'finished')
        self.assertGreater(actual['descending']['offset'], 0)
        self.assertTrue(actual['descending']['jumping'])
        self.assert_isolated(page, errors, requests)

    def test_distance_spawn_and_jump_match_at_60_and_120_hz(self):
        page, errors, requests = self.model_runner()
        outcomes=page.evaluate("""() => {
          const {createRunnerState,updateRunner,startJump,progressPercent}=runnerModel;
          return [60,120].map(hz=>{
            const state=createRunnerState([{at:.25,type:'star',height:300}]);
            const ready=JSON.stringify(state); updateRunner(state,20);
            const readyFrozen=ready===JSON.stringify(state);
            state.mode='running'; startJump(state);
            let peak=0,landing=null;
            for(let i=0;i<hz*2;i++){
              updateRunner(state,1/hz); peak=Math.max(peak,state.jumpOffset);
              if(landing===null&&!state.jumping)landing=state.elapsed;
            }
            const midway={elapsed:state.elapsed,distance:state.distance,x:state.objects[0].x,
              progress:progressPercent(state),peak,landing,offset:state.jumpOffset};
            startJump(state); updateRunner(state,.2);
            state.mode='paused'; const paused=JSON.stringify(state);
            updateRunner(state,300); startJump(state);
            const pauseFrozen=paused===JSON.stringify(state);
            state.mode='running';
            for(let i=0;i<Math.round(hz*27.8);i++)updateRunner(state,1/hz);
            const afterThirty={mode:state.mode,elapsed:state.elapsed,distance:state.distance,
              progress:progressPercent(state)};
            for(let i=0;i<hz*2;i++)updateRunner(state,1/hz);
            return {readyFrozen,pauseFrozen,midway,afterThirty,elapsed:state.elapsed,mode:state.mode,
              reason:state.reason,progress:progressPercent(state),distance:state.distance};
          });
        }""")
        for outcome in outcomes:
            self.assertTrue(outcome['readyFrozen'])
            self.assertTrue(outcome['pauseFrozen'])
            self.assertAlmostEqual(outcome['midway']['elapsed'], 2, delta=.000001)
            self.assertAlmostEqual(outcome['midway']['distance'], 400, delta=.000001)
            self.assertEqual(outcome['midway']['progress'], 6)
            self.assertAlmostEqual(outcome['midway']['peak'], 120, delta=.000001)
            self.assertAlmostEqual(outcome['midway']['landing'], .9, delta=.000001)
            self.assertEqual(outcome['midway']['offset'], 0)
            self.assertEqual(outcome['afterThirty']['mode'], 'running')
            self.assertAlmostEqual(outcome['afterThirty']['elapsed'], 30, delta=.000001)
            self.assertAlmostEqual(outcome['afterThirty']['distance'], 6000, delta=.000001)
            self.assertEqual(outcome['afterThirty']['progress'], 93)
            self.assertEqual((outcome['mode'],outcome['reason'],outcome['progress']), ('finished','clear',100))
            self.assertAlmostEqual(outcome['elapsed'], 32, delta=.000001)
            self.assertAlmostEqual(outcome['distance'], 6400, delta=.000001)
        self.assertAlmostEqual(outcomes[0]['midway']['x'],outcomes[1]['midway']['x'],delta=.000001)
        self.assert_isolated(page, errors, requests)

    def test_gameover_stops_loop_and_retry_resets_distance_score_and_jump(self):
        page,errors,requests=self.manual_runner()
        ready=self.snapshot(page)
        self.assertEqual((ready['score'],ready['progress']),(0,0))
        self.toggle(page); page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(5350,60)')
        self.assertEqual(self.snapshot(page)['score'],10)
        self.tap(page) # 木箱の直前では間に合わず、空中のままゲームオーバーになる。
        page.evaluate('runnerClock.advance(500,60)')
        stopped=self.snapshot(page)
        self.assertEqual((stopped['progress'],stopped['pending']),(16,0))
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'もう一度')
        self.assertEqual(page.locator('#runner-result-title').inner_text(),'ゲームオーバー')
        self.assertTrue(page.locator('#runner-result').is_visible())
        self.assertEqual(page.locator('#runner-result-score').inner_text(),'10')
        self.assertEqual(page.locator('#runner-result-progress').inner_text(),str(stopped['progress']))
        self.tap(page)
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'),0)
        self.assertTrue(self.snapshot(page)['image']==stopped['image'])
        self.toggle(page); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        restarted=self.snapshot(page)
        self.assertEqual((restarted['score'],restarted['progress'],restarted['pending']),(0,0,1))
        self.assert_same_scene(ready,restarted)
        self.assertTrue(page.locator('#runner-result').is_hidden())
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'一時停止')
        for _ in range(4):
            self.toggle(page)
            self.assertLessEqual(self.snapshot(page)['pending'],1)
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(4500,60)')
        self.assertEqual((self.snapshot(page)['score'],self.snapshot(page)['pending']),(10,1))
        self.assert_isolated(page,errors,requests)

    def test_full_fixed_course_can_clear_and_finished_screen_keeps_layout(self):
        page,errors,requests=self.model_runner()
        obstacles=page.evaluate("runnerModel.COURSE.filter(item=>item.type==='obstacle')")
        self.assertGreaterEqual(obstacles[0]['at']+(1008-234)/200,5)
        self.toggle(page); page.evaluate('runnerClock.step(0)')
        for obstacle in obstacles:
            # 右端出現からキャラ中心到達まで4.11秒。0.45秒前に跳ぶ。
            target_time=(obstacle['at']+3.66)*1000
            now=self.snapshot(page)['now']
            page.evaluate('ms=>runnerClock.advance(ms,60)',target_time-now)
            self.tap(page)
        now=self.snapshot(page)['now']
        page.evaluate('ms=>runnerClock.advance(ms,60)',32000-now)
        finished=self.snapshot(page)
        self.assertEqual((finished['progress'],finished['pending']),(100,0))
        self.assertEqual(page.locator('#runner-result-title').inner_text(),'クリア！')
        self.assertEqual(page.locator('#runner-result-score').inner_text(),str(finished['score']))
        self.assertEqual(page.locator('#runner-result-progress').inner_text(),'100')
        self.assertIsNotNone(finished['goal'])
        self.assertGreater(finished['score'],0)
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'),0)
        self.assertTrue(self.snapshot(page)['image']==finished['image'])
        for width,height in ((844,390),(768,1024),(1024,768)):
            page.set_viewport_size({'width':width,'height':height})
            page.evaluate('runnerClock.settle()')
            page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
            self.assert_geometry(page)
            self.assertEqual(self.snapshot(page)['pending'],0)
            self.assertTrue(page.locator('#runner-result').is_visible())
            self.assertGreaterEqual(page.locator('#runner-toggle').bounding_box()['height'],44)
        self.assert_isolated(page,errors,requests)

    def test_goal_depends_on_distance_and_collision_wins_at_the_finish(self):
        page,errors,requests=self.model_runner()
        actual=page.evaluate("""() => {
          const {createRunnerState,updateRunner,progressPercent,goalX,COURSE_LENGTH}=runnerModel;
          const state=createRunnerState([]); state.mode='running';
          updateRunner(state,30);
          const afterThirty={mode:state.mode,distance:state.distance,progress:progressPercent(state),
            goal:goalX(state)};
          state.mode='paused'; const paused=JSON.stringify(state); updateRunner(state,100);
          const frozen=paused===JSON.stringify(state);
          state.mode='running'; updateRunner(state,2);
          const finished={mode:state.mode,reason:state.reason,distance:state.distance,
            progress:progressPercent(state),goal:goalX(state)};
          const simultaneous=createRunnerState([]); simultaneous.mode='running';
          simultaneous.distance=COURSE_LENGTH-1;
          simultaneous.objects=[{id:'box',type:'obstacle',x:186}];
          updateRunner(simultaneous,.005);
          const partial=createRunnerState([]); partial.mode='running'; partial.distance=3200;
          partial.objects=[{id:'box',type:'obstacle',x:186}]; updateRunner(partial,0);
          const elapsedOnly=createRunnerState([]); elapsedOnly.mode='running'; elapsedOnly.elapsed=1000;
          updateRunner(elapsedOnly,0);
          return {length:COURSE_LENGTH,afterThirty,frozen,finished,
            simultaneous:{mode:simultaneous.mode,reason:simultaneous.reason,
              progress:progressPercent(simultaneous)},
            partial:{reason:partial.reason,progress:progressPercent(partial)},elapsedOnly:elapsedOnly.mode};
        }""")
        self.assertEqual(actual['length'],6400)
        self.assertEqual(actual['afterThirty']['mode'],'running')
        self.assertAlmostEqual(actual['afterThirty']['distance'],6000,delta=.000001)
        self.assertEqual(actual['afterThirty']['progress'],93)
        self.assertAlmostEqual(actual['afterThirty']['goal'],586,delta=.000001)
        self.assertTrue(actual['frozen'])
        self.assertEqual((actual['finished']['mode'],actual['finished']['reason'],
                          actual['finished']['progress']),('finished','clear',100))
        self.assertAlmostEqual(actual['finished']['distance'],6400,delta=.000001)
        self.assertAlmostEqual(actual['finished']['goal'],186,delta=.000001)
        self.assertEqual(actual['simultaneous'],{'mode':'finished','reason':'collision','progress':100})
        self.assertEqual(actual['partial'],{'reason':'collision','progress':50})
        self.assertEqual(actual['elapsedOnly'],'running')
        self.assert_isolated(page,errors,requests)

    def test_shiba_sprite_follows_run_and_jump_and_missing_image_uses_fallback(self):
        for broken in (False,True):
            with self.subTest(broken=broken):
                page,errors,requests=self.manual_runner(broken_image=broken)
                initial=self.snapshot(page)
                if broken:
                    self.assertIsNone(initial['sprite'])
                    self.assertEqual(page.evaluate('runnerImages[0].naturalWidth'),0)
                else:
                    sprite=initial['sprite']
                    self.assertIsNotNone(sprite)
                    self.assertTrue(sprite['src'].endswith('/assets/plush/shiba.webp'))
                    self.assertEqual((sprite['naturalWidth'],sprite['naturalHeight']),(512,512))
                    self.assertAlmostEqual(sprite['width']/sprite['height'],1,delta=.000001)
                    self.assertGreater(sprite['width'],0)
                    self.assertLessEqual(sprite['width'],100)
                    self.assertLessEqual(sprite['height'],100)
                self.assertAlmostEqual(initial['character']['x'],186,delta=.001)
                self.assertAlmostEqual(initial['character']['y'],427,delta=.001)
                self.toggle(page); page.evaluate('runnerClock.step(0)')
                page.evaluate('runnerClock.advance(1000/12,60)')
                running=self.snapshot(page)
                self.assertAlmostEqual(running['character']['y'],423,delta=.001)
                self.tap(page); page.evaluate('runnerClock.advance(450,60)')
                jumped=self.snapshot(page)
                self.assertAlmostEqual(jumped['character']['x'],186,delta=.001)
                self.assertAlmostEqual(jumped['character']['y'],307,delta=.001)
                if not broken:
                    self.assertAlmostEqual(jumped['sprite']['y'],
                      350-jumped['sprite']['height']*465/512,delta=.001)
                    self.assertEqual(jumped['sprite']['width'],initial['sprite']['width'])
                self.assertEqual(jumped['pending'],1)
                self.assertEqual(page.locator('#runner-toggle').inner_text(),'一時停止')
                self.assert_isolated(page,errors,requests)


if __name__ == '__main__':
    unittest.main()
