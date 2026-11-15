"""独立Canvas画面・距離ゴール・しば犬とトゲ岩描画。HTTPと一時ブラウザを使用する。

実行: python3 -m unittest discover -s tests -p 'runner_canvas_test.py' -v
HISTORY_MASTER_ENGINE=webkit で、導入済みのPlaywright WebKitも選択できる。
Safari実機の検証を置き換えるものではない。
"""

import functools
import http.server
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SHIBA_FRAMES = ('idle','run_1','run_2','run_3','run_4',
                'jump_up','jump_top','jump_down','land')

BUTTON_STYLE = """button => {
  const r=button.getBoundingClientRect(), s=getComputedStyle(button);
  return {x:r.x,y:r.y,width:r.width,height:r.height,
    background:s.backgroundImage,radius:s.borderRadius,shadow:s.boxShadow,
    color:s.color,textShadow:s.textShadow,font:s.fontSize,weight:s.fontWeight,
    transform:s.transform};
}"""

JUMP_PROBE = """() => {
  const {calls,state}=runnerJumpProbe;
  return {calls,mode:state?.mode,feetY:state?.feetY,velocityY:state?.velocityY,
    supportId:state?.supportId,jumpOriginY:state?.jumpOriginY,airAction:state?.airAction,
    elapsed:state?.elapsed,distance:state?.distance,score:state?.score};
}"""

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
  const scene = {character: null, markers: [], feet: [], sprite:null, goal:null,
    rocks:[],fallbackRocks:0,platforms:[],shadow:null};
  const proto = CanvasRenderingContext2D.prototype;
  const transform = proto.setTransform, rectangle = proto.fillRect, arc = proto.arc;
  const drawImage = proto.drawImage, fillText = proto.fillText, fill = proto.fill;
  const ellipse=proto.ellipse;
  proto.setTransform = function(...args) {
    scene.markers = [];
    scene.feet = [];
    scene.character = null;
    scene.sprite = null;
    scene.goal = null;
    scene.rocks = [];
    scene.fallbackRocks = 0;
    scene.platforms = [];
    scene.shadow = null;
    return transform.apply(this, args);
  };
  proto.fillRect = function(x, y, width, height) {
    if (this.fillStyle === '#79c9d4') scene.platforms.push({x,y,width,height});
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
  proto.ellipse = function(x,y,radiusX,radiusY,...rest) {
    if (x===186 && radiusX===38 && radiusY===9)
      scene.shadow={x,y,radiusX,radiusY};
    return ellipse.call(this,x,y,radiusX,radiusY,...rest);
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
    const pose=image.src?.includes('/runner/assets/shiba/') ?
      image.src.split('/').pop().replace('.webp','') : null;
    if ((pose || image.src?.endsWith('/assets/plush/shiba.webp')) && args.length === 4) {
      const [x,y,width,height] = args;
      const feet={idle:465,run_1:464,run_2:465,run_3:466,run_4:464,
        jump_up:465,jump_top:465,jump_down:464,land:466};
      const feetRatio=(feet[pose]??465)/512, matrix=this.getTransform();
      const point=matrix.transformPoint({x:x+width/2,y:y+height*feetRatio-43});
      scene.character={x:point.x*960/this.canvas.width,y:point.y*540/this.canvas.height};
      scene.sprite={x,y,width,height,src:image.src,pose:pose??'fallback',feetRatio,
        horizontalScale:matrix.a/(this.canvas.width/960),
        naturalWidth:image.naturalWidth,naturalHeight:image.naturalHeight};
    }
    if (image.src?.endsWith('/runner/assets/spike-rock.webp') && args.length === 4) {
      const [x,y,width,height] = args;
      scene.rocks.push({x,y,width,height,src:image.src,
        naturalWidth:image.naturalWidth,naturalHeight:image.naturalHeight});
    }
    return drawImage.call(this,image,...args);
  };
  proto.fill = function(...args) {
    if (this.fillStyle === '#514650') scene.fallbackRocks++;
    return fill.apply(this,args);
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
        sprite:scene.sprite,goal:scene.goal,rocks:scene.rocks,fallbackRocks:scene.fallbackRocks,
        platforms:scene.platforms,shadow:scene.shadow,
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
  const button = document.querySelector('#runner-toggle');
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
        engine = os.environ.get('HISTORY_MASTER_ENGINE', 'chromium')
        executable = os.environ.get('HISTORY_MASTER_BROWSER')
        if engine == 'chromium' and not executable:
            executable = shutil.which('chromium')
        cls.browser = getattr(cls.playwright, engine).launch(executable_path=executable)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/runner/'

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def open_runner(self, width=390, height=844, dpr=3, setup=None, broken_image=False,
                    probe=False, broken_obstacle_image=False, broken_frames=(), delayed_frames=None,
                    course=None):
        context = self.browser.new_context(
            viewport={'width': width, 'height': height},
            device_scale_factor=dpr, has_touch=True, is_mobile=True)
        self.addCleanup(context.close)
        context.add_init_script(f'({ISOLATION_GUARD})();')
        if setup:
            context.add_init_script(setup)
        page = context.new_page()
        page.set_default_timeout(5000)
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        if probe or course is not None:
            context.add_init_script('window.runnerJumpProbe={calls:0,state:null};')
            # 配信コードだけをテスト用に計測し、本番へ状態公開APIを足さない。
            script = (ROOT / 'runner/game.js').read_text(encoding='utf-8')
            if probe:
                script = script.replace('function startJump(state) {',
                    'function startJump(state) { runnerJumpProbe.calls++; runnerJumpProbe.state=state;', 1)
            if course is not None:
                signature='function createRunnerState(course = COURSE) {'
                self.assertIn(signature,script)
                script=script.replace(signature,
                    'function createRunnerState(course = '+json.dumps(course)+') {',1)
            page.route('**/runner/game.js*', lambda route: route.fulfill(
                status=200, content_type='text/javascript', body=script))
        if broken_image:
            page.route('**/assets/plush/shiba.webp', lambda route: route.fulfill(status=404, body='missing'))
        if broken_obstacle_image:
            page.route('**/runner/assets/spike-rock.webp', lambda route: route.fulfill(status=404, body='missing'))
        for frame in broken_frames:
            page.route(f'**/runner/assets/shiba/{frame}.webp',
                lambda route: route.fulfill(status=404, body='missing'))
        def defer_frame(frame):
            def hold(route):
                delayed_frames[frame]=route
            return hold
        for frame in delayed_frames or ():
            page.route(f'**/runner/assets/shiba/{frame}.webp',defer_frame(frame))
        response = page.goto(self.url, wait_until='domcontentloaded' if delayed_frames else 'load')
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

    def test_jump_button_matches_catcher_and_fits_phone_tablet_layouts(self):
        # 全CSSの後勝ちルールと実際の親余白を再現する。アプリJSは実行しない。
        css = re.search(r'<style>(.*?)</style>', (ROOT / 'index.html').read_text(), re.S)[1]
        fixture = ('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>' + css + '</style><main><section id="arcade" class="card arcade-screen">'
            '<div class="machine-wrap"><div class="machine-lower"><div class="crane-controls">'
            '<button id="crane-catch" class="crane-catch">🎯 キャッチ！</button>'
            '</div></div></div></section></main>')
        for width, height in ((375,667),(390,844),(667,375),(844,390),(768,1024),(1024,768)):
            with self.subTest(width=width, height=height):
                page, errors, requests = self.open_runner(width, height)
                self.assert_geometry(page)
                jump, toggle = page.locator('#runner-jump'), page.locator('#runner-toggle')
                self.assertTrue(jump.is_disabled())
                toggle.tap()
                self.assertFalse(jump.is_disabled())
                actual = jump.evaluate(BUTTON_STYLE)
                lower = toggle.bounding_box()
                self.assertGreaterEqual(actual['width'], 240)
                self.assertLessEqual(actual['width'], 440)
                self.assertAlmostEqual(actual['height'], 58 if width <= 640 else 62, delta=.01)
                self.assertGreaterEqual(lower['y'] - actual['y'] - actual['height'], 11.9)
                self.assertAlmostEqual(actual['x'], lower['x'], delta=.01)
                self.assertAlmostEqual(actual['width'], lower['width'], delta=.01)
                self.assertLessEqual(lower['y'] + lower['height'], height)
                self.assertEqual(jump.evaluate("b=>{const r=b.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.id}"), 'runner-jump')
                canvas = page.locator('#runner-canvas').bounding_box()
                # ボタンを重ねて大きく見せず、横画面でもCanvasの面積を確保する。
                self.assertTrue(canvas['x']+canvas['width'] <= actual['x'] or
                    canvas['y']+canvas['height'] <= actual['y'])
                if height < 500:
                    self.assertGreaterEqual(canvas['height'], 200)
                reference_page = page.context.new_page()
                reference_page.set_content(fixture)
                reference = reference_page.locator('#crane-catch')
                expected = reference.evaluate(BUTTON_STYLE)
                for prop in ('background','radius','shadow','color','textShadow','font','weight'):
                    self.assertEqual(actual[prop], expected[prop], prop)
                # 実キャッチは後勝ちCSSで74px。依頼されたジャンプ基準62/58pxと区別する。
                self.assertEqual(expected['height'], 74)
                self.assertEqual(reference_page.evaluate('runnerStorageAccesses'), [])
                def pressed(target, locator):
                    r = locator.bounding_box()
                    target.mouse.move(r['x']+r['width']/2, r['y']+r['height']/2)
                    target.mouse.down()
                    result = locator.evaluate(BUTTON_STYLE)
                    target.mouse.up()
                    return result
                active, catch_active = pressed(page, jump), pressed(reference_page, reference)
                for prop in ('shadow','transform','background','radius'):
                    self.assertEqual(active[prop], catch_active[prop], prop)
                print(f"buttons {width}x{height}: jump {actual['width']:.2f}x{actual['height']:.0f}, catch {expected['width']:.2f}x{expected['height']:.0f}")
                self.assert_isolated(page, errors, requests)

    def test_jump_button_real_taps_change_state_and_rendered_position(self):
        page, errors, requests = self.manual_runner(probe=True)
        jump, toggle = page.locator('#runner-jump'), page.locator('#runner-toggle')
        def disabled_tap():
            r = jump.bounding_box()
            page.touchscreen.tap(r['x']+r['width']/2, r['y']+r['height']/2)
        def probe():
            return page.evaluate(JUMP_PROBE)
        self.assertTrue(jump.is_disabled())
        disabled_tap()
        self.assertEqual(probe()['calls'], 0)
        # HTMLが要求するCSS/JSの識別子を揃えて旧配信物の再利用を避ける。
        versions = page.evaluate("""() => [document.querySelector('link[rel=stylesheet]').href,
          document.querySelector('script[type=module]').src].map(url=>new URL(url).searchParams.get('v'))""")
        self.assertTrue(versions[0])
        self.assertEqual(*versions)
        toggle.tap()
        page.evaluate('runnerClock.step(0)')
        jump.tap()
        self.assertEqual((probe()['calls'],probe()['supportId'],probe()['airAction']), (1,None,'jump'))
        self.assertEqual((probe()['feetY'],probe()['jumpOriginY']),(470,470))
        self.assertAlmostEqual(probe()['velocityY'],-4*120/.9,delta=.000001)
        page.evaluate('runnerClock.advance(225)')
        self.assertAlmostEqual(self.snapshot(page)['character']['y'], 337, delta=.01)
        in_air = probe()
        for _ in range(5):
            jump.tap()
        self.assertEqual(probe()['calls'], 6)  # native tapごとにclickは1回だけ。
        self.assertEqual((probe()['feetY'],probe()['velocityY']),
                         (in_air['feetY'],in_air['velocityY']))
        page.evaluate('runnerClock.advance(225)')
        self.assertAlmostEqual(self.snapshot(page)['character']['y'], 307, delta=.01)
        page.evaluate('runnerClock.advance(450)')
        self.assertEqual(probe()['supportId'],'ground')
        jump.tap()
        self.assertEqual(probe()['airAction'],'jump')
        page.evaluate('runnerClock.advance(225)')
        toggle.tap()
        self.assertTrue(jump.is_disabled())
        paused, calls = self.snapshot(page), probe()['calls']
        disabled_tap()
        self.assertEqual(probe()['calls'], calls)
        self.assertEqual(page.evaluate('runnerClock.advance(1000)'), 0)
        self.assert_same_scene(paused, self.snapshot(page))
        toggle.tap()
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(675)')
        self.assertEqual(probe()['supportId'],'ground')
        # 画面直接タップの経路も実タップで検証する。
        page.locator('#runner-canvas').tap()
        self.assertEqual(probe()['airAction'],'jump')
        page.evaluate('runnerClock.advance(900)')
        page.evaluate('runnerClock.advance(4000,60)')
        self.assertEqual(page.locator('#runner-toggle').inner_text(), 'つづける')
        toggle.tap(); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(3500,60)')
        self.assertEqual(page.locator('#runner-result-title').inner_text(), 'ゲームオーバー')
        self.assertTrue(jump.is_disabled())
        stopped, calls = self.snapshot(page), probe()['calls']
        disabled_tap()
        self.assertEqual(probe()['calls'], calls)
        self.assertEqual(page.evaluate('runnerClock.advance(1000)'), 0)
        self.assert_same_scene(stopped, self.snapshot(page))
        self.assert_isolated(page, errors, requests)

    def test_jump_button_real_mouse_enter_and_space_use_one_action(self):
        page, errors, requests = self.manual_runner(probe=True)
        jump = page.locator('#runner-jump')
        page.locator('#runner-toggle').click()
        page.evaluate('runnerClock.step(0)')
        for count, action in enumerate((lambda: jump.click(), lambda: jump.press('Enter'), lambda: jump.press('Space')), 1):
            action()
            actual = page.evaluate(JUMP_PROBE)
            self.assertEqual((actual['calls'],actual['supportId'],actual['airAction']), (count,None,'jump'))
            self.assertEqual((actual['feetY'],actual['jumpOriginY']),(470,470))
            self.assertAlmostEqual(actual['velocityY'],-4*120/.9,delta=.000001)
            page.evaluate('runnerClock.advance(225)')
            self.assertAlmostEqual(self.snapshot(page)['character']['y'], 337, delta=.01)
            page.evaluate('runnerClock.advance(675)')
            self.assertEqual(page.evaluate(JUMP_PROBE)['supportId'],'ground')
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
                self.assertTrue(page.locator('#runner-toggle').is_disabled())
                self.assertTrue(page.locator('#runner-jump').is_disabled())
                self.assert_isolated(page, errors, requests)

    def manual_runner(self, broken_image=False, probe=False, broken_obstacle_image=False,
                      width=390, height=844, dpr=3, broken_frames=(),course=None):
        page, errors, requests = self.open_runner(width, height, dpr, setup=MANUAL_FRAMES,
            broken_image=broken_image, probe=probe, broken_obstacle_image=broken_obstacle_image,
            broken_frames=broken_frames,course=course)
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


    def model_runner(self,probe=False):
        page, errors, requests = self.manual_runner(probe=probe)
        # 通常のES Module APIだけを使い、実ゲームの非公開状態へテスト用hookを追加しない。
        page.evaluate("async () => { window.runnerModel = await import(document.querySelector('script[type=module]').src); }")
        return page, errors, requests

    def test_jump_has_fixed_height_parabolic_motion_and_exact_landing(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState, updateRunner, startJump, GROUND_Y, JUMP} = runnerModel;
          const state=createRunnerState([]); state.mode='running';
          updateRunner(state,1);
          const idle={feet:state.feetY,support:state.supportId,velocity:state.velocityY,air:state.airAction};
          startJump(state); updateRunner(state,.225);
          const rising={height:state.jumpOriginY-state.feetY,velocity:state.velocityY};
          const airborne=JSON.stringify(state);
          for(let i=0;i<20;i++)startJump(state);
          const repeatedIgnored=airborne===JSON.stringify(state);
          updateRunner(state,.225);
          const apex={height:state.jumpOriginY-state.feetY,velocity:state.velocityY};
          updateRunner(state,.225);
          const descending={height:state.jumpOriginY-state.feetY,velocity:state.velocityY};
          updateRunner(state,.225);
          const landed={feet:state.feetY,support:state.supportId,velocity:state.velocityY,air:state.airAction};
          updateRunner(state,1);
          const grounded=state.feetY===GROUND_Y&&state.supportId==='ground';
          startJump(state); updateRunner(state,.45);
          return {idle,rising,repeatedIgnored,apex,descending,landed,grounded,
            secondApex:state.jumpOriginY-state.feetY,ground:GROUND_Y,config:JUMP};
        }""")
        self.assertEqual(actual['idle'], {'feet':actual['ground'],'support':'ground','velocity':0,'air':None})
        self.assertAlmostEqual(actual['rising']['height'], 90, delta=.000001)
        self.assertLess(actual['rising']['velocity'], 0)
        self.assertTrue(actual['repeatedIgnored'])
        self.assertAlmostEqual(actual['apex']['height'], 120, delta=.000001)
        self.assertAlmostEqual(actual['apex']['velocity'], 0, delta=.000001)
        self.assertAlmostEqual(actual['descending']['height'], 90, delta=.000001)
        self.assertGreater(actual['descending']['velocity'], 0)
        self.assertEqual(actual['landed'], {'feet':actual['ground'],'support':'ground','velocity':0,'air':None})
        self.assertTrue(actual['grounded'])
        self.assertAlmostEqual(actual['secondApex'], 120, delta=.000001)
        self.assert_isolated(page, errors, requests)

    def test_platform_landings_use_the_top_and_horizontal_overlap_at_crossing(self):
        page,errors,requests=self.model_runner()
        actual=page.evaluate("""() => {
          const {createRunnerState,updateRunner,startJump,platformBounds,JUMP}=runnerModel;
          function airborne(feet,velocity,object) {
            const state=createRunnerState([]);state.mode='running';state.feetY=feet;
            state.velocityY=velocity;state.supportId=null;state.airAction='fall';
            state.objects=[object];return state;
          }
          const platform={id:'upper',type:'platform',x:186};
          const above=airborne(370,200,{...platform});updateRunner(above,.12);
          const below=createRunnerState([]);below.mode='running';
          below.objects=[{...platform,width:400}];startJump(below);updateRunner(below,.225);
          const rising={feet:below.feetY,velocity:below.velocityY,support:below.supportId};
          updateRunner(below,.485);
          const side=airborne(400,100,{...platform});updateRunner(side,.1);
          const sidePass={feet:side.feetY,support:side.supportId,mode:side.mode};
          updateRunner(side,1);
          const walking=createRunnerState([]);walking.mode='running';walking.objects=[{...platform}];
          updateRunner(walking,.6);
          // 幅10pxの台が、足との重なりを着地時刻の前後で失う／得るケース。
          const departing=airborne(389,200,{id:'departing',type:'platform',x:161.5,width:10});
          updateRunner(departing,1/120);
          const arriving=airborne(389,200,{id:'arriving',type:'platform',x:211.5,width:10});
          updateRunner(arriving,1/120);
          const landThenFall=airborne(389.7,100,{id:'edge',type:'platform',x:71.8});
          updateRunner(landThenFall,1/120);
          // 同じ更新内で上昇→頂点→下降する、ほぼ最大高度の台も着地できる。
          const apex=airborne(350+.5*JUMP.gravity*.004**2,-JUMP.gravity*.004,
            {id:'apex',type:'platform',x:186,height:119.999});
          apex.airAction='jump';updateRunner(apex,1/120);
          function result(state){return {feet:state.feetY,velocity:state.velocityY,
            support:state.supportId,mode:state.mode};}
          return {bounds:platformBounds(platform),above:result(above),rising,below:result(below),
            sidePass,sideEnd:result(side),walking:result(walking),
            departing:result(departing),arriving:result(arriving),landThenFall:result(landThenFall),
            apex:result(apex)};
        }""")
        self.assertEqual(actual['bounds'],{'left':91,'right':281,'top':390,'bottom':422,
                                            'width':190,'thickness':32})
        self.assertEqual(actual['above'],{'feet':390,'velocity':0,'support':'upper','mode':'running'})
        self.assertAlmostEqual(actual['rising']['feet'],380,delta=.000001)
        self.assertLess(actual['rising']['velocity'],0)
        self.assertIsNone(actual['rising']['support'])
        self.assertEqual(actual['below'],{'feet':390,'velocity':0,'support':'upper','mode':'running'})
        self.assertGreater(actual['sidePass']['feet'],400)
        self.assertIsNone(actual['sidePass']['support'])
        self.assertEqual(actual['sidePass']['mode'],'running')
        for key in ('sideEnd','walking'):
            self.assertEqual(actual[key],{'feet':470,'velocity':0,'support':'ground','mode':'running'})
        self.assertGreater(actual['departing']['feet'],390)
        self.assertIsNone(actual['departing']['support'])
        self.assertEqual(actual['arriving'],{'feet':390,'velocity':0,'support':'arriving','mode':'running'})
        self.assertIsNone(actual['landThenFall']['support'])
        self.assertAlmostEqual(actual['landThenFall']['feet'],390.01112757201645,delta=.000001)
        self.assertAlmostEqual(actual['landThenFall']['velocity'],5.135802469135839,delta=.000001)
        self.assertAlmostEqual(actual['apex']['feet'],350.001,delta=.000001)
        self.assertEqual((actual['apex']['support'],actual['apex']['velocity']),('apex',0))
        self.assert_isolated(page,errors,requests)

    def test_platform_jump_keeps_height_and_duration_at_60_and_120_hz(self):
        page,errors,requests=self.model_runner()
        outcomes=page.evaluate("""() => [60,120].map(hz=>{
          const {createRunnerState,updateRunner,startJump,characterBob,characterPose,shadowY}=runnerModel;
          const state=createRunnerState([]);state.mode='running';state.feetY=390;state.supportId='upper';
          state.objects=[{id:'upper',type:'platform',x:186,width:1000}];
          const supported={bob:characterBob(state),shadow:shadowY(state)};
          const accepted=startJump(state),samples=[];
          function advance(seconds){const count=Math.round(seconds*hz);
            for(let i=0;i<count;i++)updateRunner(state,seconds/count);}
          for(let i=0;i<4;i++){
            advance(.225);samples.push({height:state.jumpOriginY-state.feetY,velocity:state.velocityY});
            if(i===1){state.mode='paused';const paused=JSON.stringify(state);
              updateRunner(state,20);startJump(state);
              samples[i].frozen=paused===JSON.stringify(state);
              samples[i].pose=characterPose(state);state.mode='running';}
          }
          return {accepted,supported,samples,origin:state.jumpOriginY,feet:state.feetY,
            support:state.supportId,velocity:state.velocityY,time:state.elapsed,distance:state.distance,
            bob:characterBob(state),shadow:shadowY(state),pose:characterPose(state)};
        })""")
        for outcome in outcomes:
            self.assertTrue(outcome['accepted'])
            self.assertEqual(outcome['supported'],{'bob':0,'shadow':390})
            for sample,height in zip(outcome['samples'],(90,120,90,0)):
                self.assertAlmostEqual(sample['height'],height,delta=.000001)
            self.assertLess(outcome['samples'][0]['velocity'],0)
            self.assertAlmostEqual(outcome['samples'][1]['velocity'],0,delta=.000001)
            self.assertTrue(outcome['samples'][1]['frozen'])
            self.assertEqual(outcome['samples'][1]['pose'],'idle')
            self.assertGreater(outcome['samples'][2]['velocity'],0)
            self.assertEqual((outcome['origin'],outcome['feet'],outcome['support'],outcome['velocity']),
                             (390,390,'upper',0))
            self.assertAlmostEqual(outcome['time'],.9,delta=.000001)
            self.assertAlmostEqual(outcome['distance'],180,delta=.000001)
            self.assertEqual((outcome['bob'],outcome['shadow'],outcome['pose']),(0,390,'land'))
        self.assert_isolated(page,errors,requests)

    def test_platform_edge_fall_is_continuous_and_lands_lower_or_on_ground(self):
        page,errors,requests=self.model_runner()
        outcomes=page.evaluate("""() => [60,120].flatMap(hz=>[false,true].map(lower=>{
          const {createRunnerState,updateRunner,startJump,characterPose,shadowY,JUMP,CHARACTER_SET}=runnerModel;
          const state=createRunnerState([]);state.mode='running';state.feetY=390;state.supportId='upper';
          state.objects=[{id:'upper',type:'platform',x:80}];
          if(lower)state.objects.push({id:'lower',type:'platform',x:220,width:240,height:40});
          function advance(seconds){const count=Math.max(1,Math.round(seconds*hz));
            for(let i=0;i<count;i++)updateRunner(state,seconds/count);}
          advance(.04);const before={feet:state.feetY,support:state.supportId};
          advance(.01);const falling={feet:state.feetY,velocity:state.velocityY,support:state.supportId,
            action:state.airAction,pose:characterPose(state),shadow:shadowY(state)};
          const inAir=JSON.stringify(state),accepted=startJump(state),unchanged=JSON.stringify(state)===inAir;
          state.mode='paused';const paused=JSON.stringify(state);updateRunner(state,10);
          const frozen=JSON.stringify(state)===paused;state.mode='running';advance(.55);
          return {hz,lower,before,falling,accepted,unchanged,frozen,feet:state.feetY,
            support:state.supportId,velocity:state.velocityY,landingAt:state.landingUntil-CHARACTER_SET.landingSeconds,
            expectedLanding:.045+Math.sqrt(2*(lower?40:80)/JUMP.gravity),distance:state.distance};
        }))""")
        for outcome in outcomes:
            self.assertEqual(outcome['before'],{'feet':390,'support':'upper'})
            falling=outcome['falling']
            self.assertAlmostEqual(falling['feet'],390+.5*(8*120/.9**2)*.005**2,delta=.000001)
            self.assertAlmostEqual(falling['velocity'],(8*120/.9**2)*.005,delta=.000001)
            self.assertEqual((falling['support'],falling['action'],falling['pose']),
                             (None,'fall','jump_down'))
            self.assertEqual(falling['shadow'],430 if outcome['lower'] else 470)
            self.assertFalse(outcome['accepted'])
            self.assertTrue(outcome['unchanged'])
            self.assertTrue(outcome['frozen'])
            self.assertEqual((outcome['feet'],outcome['support'],outcome['velocity']),
                (430,'lower',0) if outcome['lower'] else (470,'ground',0))
            self.assertAlmostEqual(outcome['landingAt'],outcome['expectedLanding'],delta=.000001)
            self.assertAlmostEqual(outcome['distance'],120,delta=.000001)
        self.assert_isolated(page,errors,requests)

    def test_real_taps_land_and_jump_on_platform_with_shadow_pause_restore_and_retry(self):
        course=[{'at':0,'type':'platform'},{'at':0,'type':'star','height':80},
                {'at':5.5,'type':'obstacle'},{'at':8.5,'type':'obstacle'}]
        page,errors,requests=self.manual_runner(probe=True,course=course)
        self.assertEqual(self.snapshot(page)['shadow']['y'],470)
        page.locator('#runner-toggle').tap();page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(3400,60)')
        ground=self.snapshot(page)
        self.assertEqual(len(ground['platforms']),1)
        self.assertAlmostEqual(ground['platforms'][0]['x'],233,delta=.000001)
        self.assertAlmostEqual(ground['platforms'][0]['y'],390,delta=.000001)
        self.assertEqual((ground['platforms'][0]['width'],ground['platforms'][0]['height']),(190,32))
        self.assertEqual(ground['shadow']['y'],470)
        page.locator('#runner-jump').tap()
        takeoff=page.evaluate(JUMP_PROBE)
        self.assertEqual((takeoff['supportId'],takeoff['airAction'],takeoff['jumpOriginY']),
                         (None,'jump',470))
        page.evaluate('runnerClock.advance(450,60)')
        apex=self.snapshot(page)
        self.assertEqual(apex['sprite']['pose'],'jump_top')
        self.assertAlmostEqual(apex['character']['y'],307,delta=.001)
        self.assertEqual(apex['shadow']['y'],390)
        page.evaluate('runnerClock.advance(270,60)')
        landed=self.snapshot(page);state=page.evaluate(JUMP_PROBE)
        # 最初にspawnした台のidは0。false扱いにせず支持面として使う。
        self.assertEqual((state['feetY'],state['supportId'],state['velocityY'],state['airAction']),
                         (390,0,0,None))
        self.assertEqual(landed['sprite']['pose'],'land')
        self.assertAlmostEqual(landed['sprite']['y']+landed['sprite']['height']*landed['sprite']['feetRatio'],
                               390,delta=.001)
        self.assertAlmostEqual(landed['character']['y'],347,delta=.001)
        self.assertEqual((landed['shadow']['y'],landed['score']),(390,10))
        page.evaluate('runnerClock.advance(130,60)')
        walking=self.snapshot(page)
        self.assertTrue(walking['sprite']['pose'].startswith('run_'))
        self.assertAlmostEqual(walking['character']['y'],347,delta=.001)
        self.assertEqual(walking['shadow']['y'],390)
        page.locator('#runner-toggle').tap()
        paused=self.snapshot(page);paused_state=page.evaluate(JUMP_PROBE)
        self.assertEqual((paused['sprite']['pose'],paused['pending']),('idle',0))
        page.evaluate("""() => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
        }""")
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'),0)
        self.assertEqual(page.evaluate(JUMP_PROBE),paused_state)
        self.assertEqual(self.snapshot(page)['image'],paused['image'])
        page.evaluate("""() => {
          delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
        }""")
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'再開')
        for width,height in ((375,667),(390,844),(667,375),(844,390),(768,1024),(1024,768)):
            with self.subTest(width=width,height=height):
                page.set_viewport_size({'width':width,'height':height})
                page.evaluate('runnerClock.settle()');page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                self.assert_geometry(page)
                restored=self.snapshot(page)
                self.assertEqual((restored['pending'],restored['sprite']['pose'],restored['shadow']['y']),
                                 (0,'idle',390))
                self.assertEqual(restored['platforms'],walking['platforms'])
                self.assert_same_scene(paused,restored)
                self.assertEqual(page.evaluate(JUMP_PROBE),paused_state)
        page.locator('#runner-toggle').tap();page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assertEqual(self.snapshot(page)['sprite']['pose'],walking['sprite']['pose'])
        page.evaluate('runnerClock.advance(450,60)')
        falling=self.snapshot(page);air=page.evaluate(JUMP_PROBE)
        self.assertGreater(air['feetY'],390)
        self.assertEqual((air['supportId'],air['airAction']),(None,'fall'))
        self.assertEqual((falling['sprite']['pose'],falling['shadow']['y']),('jump_down',470))
        page.locator('#runner-jump').tap()
        ignored=page.evaluate(JUMP_PROBE)
        self.assertEqual((ignored['feetY'],ignored['velocityY'],ignored['airAction']),
                         (air['feetY'],air['velocityY'],'fall'))
        page.evaluate('runnerClock.advance(500,60)')
        self.assertEqual((page.evaluate(JUMP_PROBE)['feetY'],page.evaluate(JUMP_PROBE)['supportId']),
                         (470,'ground'))
        page.evaluate('runnerClock.advance(5000,20)')
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'つづける')
        self.toggle(page); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(3500,60)')
        self.assertEqual(page.locator('#runner-result-title').inner_text(),'ゲームオーバー')
        self.assertEqual((self.snapshot(page)['score'],self.snapshot(page)['pending']),(10,0))
        page.locator('#runner-toggle').tap();page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        reset=self.snapshot(page)
        self.assertEqual((reset['score'],reset['progress'],reset['shadow']['y']),(0,0,470))
        self.assertEqual(len(reset['platforms']),1)
        self.assertAlmostEqual(reset['platforms'][0]['x'],913,delta=.000001)
        self.assertEqual((reset['platforms'][0]['y'],reset['platforms'][0]['width'],reset['platforms'][0]['height']),
                         (390,190,32))
        self.assertAlmostEqual(reset['character']['y'],427,delta=.001)
        page.locator('#runner-jump').tap()
        fresh=page.evaluate(JUMP_PROBE)
        self.assertEqual((fresh['feetY'],fresh['jumpOriginY'],fresh['elapsed'],fresh['distance'],fresh['score']),
                         (470,470,0,0,0))
        self.assertEqual((fresh['supportId'],fresh['airAction']),(None,'jump'))
        self.assertAlmostEqual(fresh['velocityY'],-4*120/.9,delta=.000001)
        # リトライ後も同じ台へ乗り、着地の絵が出ている間に再ジャンプできる。
        page.evaluate('runnerClock.advance(3400,60)')
        page.locator('#runner-jump').tap();page.evaluate('runnerClock.advance(720,60)')
        self.assertEqual(page.evaluate(JUMP_PROBE)['supportId'],0)
        self.assertEqual(self.snapshot(page)['sprite']['pose'],'land')
        page.locator('#runner-jump').tap()
        self.assertEqual(page.evaluate(JUMP_PROBE)['jumpOriginY'],390)
        page.evaluate('runnerClock.advance(450,60)')
        upper_apex=self.snapshot(page)
        self.assertAlmostEqual(page.evaluate(JUMP_PROBE)['feetY'],270,delta=.000001)
        self.assertAlmostEqual(upper_apex['character']['y'],227,delta=.001)
        self.assertEqual((upper_apex['sprite']['pose'],upper_apex['shadow']['y']),('jump_top',390))
        self.assert_isolated(page,errors,requests)

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
                           {id:'approaching',type:'obstacle',x:248}];
          updateRunner(delayed,.05);
          return {miss,mode:state.mode,reason:state.reason,score:state.score,
            progress:progressPercent(state),frozen:JSON.stringify(state)===stopped,
            delayedScore:delayed.score,delayedReason:delayed.reason};
        }""")
        self.assertEqual(actual, {'miss':'running','mode':'hurt','reason':'collision',
                                  'score':20,'progress':0,'frozen':True,
                                  'delayedScore':30,'delayedReason':'collision'})
        self.assert_isolated(page, errors, requests)

    def test_two_lives_continue_preserves_score_stars_and_physics_at_60_and_120_hz(self):
        page, errors, requests = self.model_runner()
        outcomes = page.evaluate("""() => [60,120].flatMap(hz => ['ground','jump','platform'].map(place => {
          const m=runnerModel, state=m.createRunnerState([]);
          const initial={lives:state.lives,shield:state.invincibleRemaining};
          state.mode='running';state.score=20;
          if(place==='jump'){m.startJump(state);m.updateRunner(state,.83);}
          if(place==='platform'){
            state.feetY=440;state.supportId='ledge';state.jumpOriginY=440;
            state.objects=[{id:'ledge',type:'platform',height:30,width:500,x:186}];
          }
          state.objects.push({id:'taken',type:'star',height:470-state.feetY,x:186});
          m.updateRunner(state,0); // 衝突より前に取得済みのスター。
          state.objects.push({id:'future',type:'star',height:0,x:800},
                             {id:'rock',type:'obstacle',x:186});
          m.updateRunner(state,0);
          const hurt=structuredClone(state), frozen=JSON.stringify(state);
          m.updateRunner(state,300);const jumped=m.startJump(state);
          const stopped=frozen===JSON.stringify(state);
          m.resumeRunner(state);
          const resumed=structuredClone(state);
          m.resumeRunner(state); // 続行の重複入力でも無敵時間と物理状態を変えない。
          const duplicate=JSON.stringify(state)===JSON.stringify(resumed);
          for(let i=0;i<hz/2;i++)m.updateRunner(state,1/hz);
          const halfway=structuredClone(state);
          state.mode='paused';const paused=JSON.stringify(state);
          m.updateRunner(state,300);m.startJump(state);
          const pauseFrozen=paused===JSON.stringify(state);
          m.resumeRunner(state);
          const shieldAfterPause=state.invincibleRemaining;
          for(let i=0;i<hz/2;i++)m.updateRunner(state,1/hz);
          const safe={mode:state.mode,lives:state.lives,shield:state.invincibleRemaining,
            score:state.score,ids:state.objects.map(o=>o.id)};
          state.objects.push({id:'second',type:'obstacle',x:186});
          // 最後の衝突だけは地面上に置き、当たり判定を確実にする。
          state.feetY=470;state.velocityY=0;state.supportId='ground';
          m.updateRunner(state,0);
          const ended=JSON.stringify(state);m.updateRunner(state,300);m.resumeRunner(state);
          return {hz,place,initial,hurt,resumed,jumped,stopped,duplicate,halfway,pauseFrozen,
            shieldAfterPause,safe,final:{mode:state.mode,lives:state.lives,reason:state.reason},
            finalFrozen:ended===JSON.stringify(state),retry:m.createRunnerState(state)};
        }))""")
        for item in outcomes:
            with self.subTest(hz=item['hz'], place=item['place']):
                self.assertEqual(item['initial'], {'lives':2,'shield':0})
                hurt, resumed = item['hurt'], item['resumed']
                self.assertEqual((hurt['mode'],hurt['lives'],hurt['reason']), ('hurt',1,'collision'))
                self.assertEqual(hurt['score'],30)
                self.assertNotIn('taken',[o['id'] for o in hurt['objects']])
                self.assertIn('future',[o['id'] for o in hurt['objects']])
                self.assertFalse(item['jumped'])
                self.assertTrue(item['stopped'])
                self.assertTrue(item['duplicate'])
                self.assertEqual((resumed['mode'],resumed['lives'],resumed['invincibleRemaining']),
                                 ('running',1,1))
                for field in ('distance','elapsed','animationTime','score','objects','nextSpawn',
                              'feetY','velocityY','supportId','airAction','jumpOriginY','landingUntil'):
                    self.assertEqual(resumed[field],hurt[field],field)
                self.assertAlmostEqual(item['halfway']['invincibleRemaining'],.5,delta=1e-6)
                self.assertTrue(item['pauseFrozen'])
                self.assertAlmostEqual(item['shieldAfterPause'],.5,delta=1e-6)
                self.assertEqual((item['safe']['mode'],item['safe']['lives'],item['safe']['score']),
                                 ('running',1,30))
                self.assertAlmostEqual(item['safe']['shield'],0,delta=1e-6)
                self.assertEqual(item['final'],{'mode':'finished','lives':0,'reason':'collision'})
                self.assertTrue(item['finalFrozen'])
                retry=item['retry']
                self.assertEqual((retry['lives'],retry['invincibleRemaining'],retry['score'],retry['distance']),
                                 (2,0,0,0))
                self.assertEqual(retry['objects'],[])
                if item['place']=='platform':
                    self.assertEqual((item['halfway']['feetY'],item['halfway']['supportId']),(440,'ledge'))
                if item['place']=='jump':
                    self.assertEqual((item['halfway']['feetY'],item['halfway']['supportId']),(470,'ground'))
        self.assert_isolated(page, errors, requests)

    def test_rock_collision_uses_actual_height_and_a_jump_clears_the_rock(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState,updateRunner,startJump}=runnerModel;
          const early=createRunnerState([]); early.mode='running'; startJump(early);
          early.objects=[{id:'rock',type:'obstacle',x:186}]; updateRunner(early,0);
          const over=createRunnerState([]); over.mode='running'; startJump(over);
          updateRunner(over,.45);
          over.objects=[{id:'rock',type:'obstacle',x:186}]; updateRunner(over,0);
          const apex={mode:over.mode,height:over.jumpOriginY-over.feetY};
          updateRunner(over,.45);
          const passed={mode:over.mode,feet:over.feetY,support:over.supportId};
          const descending=createRunnerState([]); descending.mode='running'; startJump(descending);
          updateRunner(descending,.83);
          descending.objects=[{id:'rock',type:'obstacle',x:186}]; updateRunner(descending,0);
          return {early:early.mode,apex,passed,descending:{mode:descending.mode,
            height:descending.jumpOriginY-descending.feetY,support:descending.supportId}};
        }""")
        self.assertEqual(actual['early'], 'hurt')
        self.assertEqual(actual['apex']['mode'], 'running')
        self.assertAlmostEqual(actual['apex']['height'], 120, delta=.000001)
        self.assertEqual(actual['passed'], {'mode':'running','feet':470,'support':'ground'})
        self.assertEqual(actual['descending']['mode'], 'hurt')
        self.assertGreater(actual['descending']['height'], 0)
        self.assertIsNone(actual['descending']['support'])
        self.assert_isolated(page, errors, requests)

    def test_spike_rock_transparent_corner_misses_but_body_and_tip_hit(self):
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const {createRunnerState,updateRunner,CHARACTER_X,GROUND_Y,COLLISION,OBSTACLE_IMAGE}=runnerModel;
          function at(relativeX,relativeY) {
            const state=createRunnerState([]); state.mode='running';
            // 時刻0の実際の円中心を置き、透明な角と細い中央トゲを別々に検査する。
            state.feetY=GROUND_Y+relativeY+43;state.supportId=null;state.airAction='fall';
            state.objects=[{id:'rock',type:'obstacle',x:CHARACTER_X-relativeX}];
            updateRunner(state,0);
            return {mode:state.mode,reason:state.reason};
          }
          return {corner:at(51,-61),tip:at(0,-80),body:at(0,-20),outside:at(100,-20),
            width:OBSTACLE_IMAGE.width,radius:COLLISION.characterRadius};
        }""")
        self.assertEqual(actual['corner'], {'mode':'running','reason':None})
        self.assertEqual(actual['outside'], {'mode':'running','reason':None})
        for part in ('tip', 'body'):
            self.assertEqual(actual[part], {'mode':'hurt','reason':'collision'}, part)
        self.assertEqual((actual['width'], actual['radius']), (80,28))
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
              updateRunner(state,1/hz); peak=Math.max(peak,state.jumpOriginY-state.feetY);
              if(landing===null&&state.supportId==='ground')landing=state.elapsed;
            }
            const midway={elapsed:state.elapsed,distance:state.distance,x:state.objects[0].x,
              progress:progressPercent(state),peak,landing,height:state.jumpOriginY-state.feetY};
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
            self.assertEqual(outcome['midway']['height'], 0)
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
        page.evaluate('runnerClock.advance(5330,60)')
        self.assertEqual(self.snapshot(page)['score'],10)
        self.tap(page) # トゲ岩の直前では間に合わず、空中のまま最初の衝突になる。
        page.evaluate('runnerClock.advance(500,60)')
        stopped=self.snapshot(page)
        self.assertEqual((stopped['progress'],stopped['pending']),(16,0))
        self.assertEqual(stopped['sprite']['pose'],'idle')
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'つづける')
        self.assertTrue(page.locator('#runner-result').is_hidden())
        self.assertEqual(page.locator('#runner-lives').inner_text(),'1')
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'),0)
        self.toggle(page); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assertEqual(self.snapshot(page)['progress'],stopped['progress'])
        page.evaluate('runnerClock.advance(3500,60)')
        stopped=self.snapshot(page)
        self.assertEqual(page.locator('#runner-lives').inner_text(),'0')
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'もう一度')
        self.assertEqual(page.locator('#runner-result-title').inner_text(),'ゲームオーバー')
        self.assertTrue(page.locator('#runner-result').is_visible())
        self.assertEqual(page.locator('#runner-result-score').inner_text(),str(stopped['score']))
        self.assertEqual(page.locator('#runner-result-progress').inner_text(),str(stopped['progress']))
        self.tap(page)
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'),0)
        self.assertTrue(self.snapshot(page)['image']==stopped['image'])
        self.toggle(page); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        restarted=self.snapshot(page)
        self.assertEqual((restarted['score'],restarted['progress'],restarted['pending']),(0,0,1))
        self.assertEqual(page.locator('#runner-lives').inner_text(),'2')
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
        for hz,use_platform in ((60,False),(60,True),(120,False),(120,True)):
            with self.subTest(hz=hz,use_platform=use_platform):
                page,errors,requests=self.model_runner(probe=True)
                obstacles=page.evaluate("runnerModel.COURSE.filter(item=>item.type==='obstacle')")
                self.assertEqual(len(obstacles),8)
                self.assertEqual(page.evaluate("runnerModel.COURSE.filter(item=>item.type==='star').length"),10)
                self.assertEqual(page.evaluate("runnerModel.COURSE.filter(item=>item.type==='platform')"),
                                 [{'at':26,'type':'platform'}])
                # 画像全体の幅まで含めた保守的な見積もりでも、最初の接触は5秒以降。
                earliest=page.evaluate("""() => {const m=runnerModel;
                  return m.COURSE.find(item=>item.type==='obstacle').at+
                    (1008-m.CHARACTER_X-m.OBSTACLE_IMAGE.width/2-m.COLLISION.characterRadius)/m.SCROLL_SPEED;
                }""")
                self.assertGreaterEqual(earliest,5)
                self.toggle(page); page.evaluate('runnerClock.step(0)')
                for obstacle in obstacles:
                    # 右端出現からキャラ中心到達まで4.11秒。0.45秒前に跳ぶ。
                    target_time=(obstacle['at']+3.66)*1000
                    now=self.snapshot(page)['now']
                    page.evaluate('args=>runnerClock.advance(...args)',[target_time-now,hz])
                    self.tap(page)
                if use_platform:
                    now=self.snapshot(page)['now']
                    page.evaluate('args=>runnerClock.advance(...args)',[29400-now,hz])
                    self.tap(page)
                    page.evaluate('args=>runnerClock.advance(...args)',[720,hz])
                    on_platform=page.evaluate(JUMP_PROBE)
                    self.assertEqual(on_platform['feetY'],390)
                    self.assertIsNotNone(on_platform['supportId'])
                    self.assertNotEqual(on_platform['supportId'],'ground')
                    self.assertEqual(self.snapshot(page)['shadow']['y'],390)
                now=self.snapshot(page)['now']
                page.evaluate('args=>runnerClock.advance(...args)',[32000-now,hz])
                finished=self.snapshot(page)
                self.assertEqual((finished['progress'],finished['pending']),(100,0))
                self.assertEqual(page.locator('#runner-result-title').inner_text(),'クリア！')
                self.assertEqual(page.locator('#runner-result-score').inner_text(),str(finished['score']))
                self.assertEqual(page.locator('#runner-result-progress').inner_text(),'100')
                self.assertIsNotNone(finished['goal'])
                self.assertEqual(finished['sprite']['pose'],'idle')
                self.assertEqual(finished['score'],100)
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
          simultaneous.objects=[{id:'box',type:'obstacle',x:186},
            {id:'finish-star',type:'star',height:0,x:186}];
          updateRunner(simultaneous,.005);
          const firstAtGoal={mode:simultaneous.mode,reason:simultaneous.reason,
            progress:progressPercent(simultaneous),lives:simultaneous.lives,score:simultaneous.score};
          runnerModel.resumeRunner(simultaneous);updateRunner(simultaneous,0);
          const continuedAtGoal=JSON.stringify(simultaneous);updateRunner(simultaneous,1);
          const second=createRunnerState([]);second.mode='running';second.lives=1;
          second.distance=COURSE_LENGTH-1;
          second.objects=[{id:'box',type:'obstacle',x:186},
            {id:'finish-star',type:'star',height:0,x:186}];updateRunner(second,.005);
          const partial=createRunnerState([]); partial.mode='running'; partial.distance=3200;
          partial.objects=[{id:'box',type:'obstacle',x:186}]; updateRunner(partial,0);
          const elapsedOnly=createRunnerState([]); elapsedOnly.mode='running'; elapsedOnly.elapsed=1000;
          updateRunner(elapsedOnly,0);
          return {length:COURSE_LENGTH,afterThirty,frozen,finished,
            simultaneous:firstAtGoal,
            continuedAtGoal:{mode:simultaneous.mode,reason:simultaneous.reason,
              lives:simultaneous.lives,score:simultaneous.score,distance:simultaneous.distance,
              starCount:simultaneous.objects.filter(o=>o.type==='star').length,
              frozen:continuedAtGoal===JSON.stringify(simultaneous)},
            secondAtGoal:{mode:second.mode,reason:second.reason,lives:second.lives,score:second.score,
              progress:progressPercent(second),starCount:second.objects.filter(o=>o.type==='star').length},
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
        self.assertEqual(actual['simultaneous'],
                         {'mode':'hurt','reason':'collision','progress':100,'lives':1,'score':0})
        self.assertEqual(actual['continuedAtGoal'],
                         {'mode':'finished','reason':'clear','lives':1,'score':10,
                          'distance':6400,'starCount':0,'frozen':True})
        self.assertEqual(actual['secondAtGoal'],
                         {'mode':'finished','reason':'collision','lives':0,'score':0,
                          'progress':100,'starCount':1})
        self.assertEqual(actual['partial'],{'reason':'collision','progress':50})
        self.assertEqual(actual['elapsedOnly'],'running')
        self.assert_isolated(page,errors,requests)

    def test_shiba_sprite_follows_run_and_jump_and_missing_image_uses_fallback(self):
        for broken in (False,True):
            with self.subTest(broken=broken):
                page,errors,requests=self.manual_runner(broken_image=broken,
                    broken_frames=SHIBA_FRAMES if broken else ())
                initial=self.snapshot(page)
                def pose(expected):
                    scene=self.snapshot(page)
                    if broken:
                        self.assertIsNone(scene['sprite'])
                    else:
                        sprite=scene['sprite']
                        self.assertEqual(sprite['pose'],expected)
                        self.assertEqual((sprite['naturalWidth'],sprite['naturalHeight']),(512,512))
                        self.assertEqual((sprite['width'],sprite['height']),(100,100))
                        self.assertAlmostEqual(sprite['horizontalScale'],1,delta=.000001)
                        self.assertAlmostEqual(sprite['x']+sprite['width']/2,186,delta=.001)
                    return scene
                if broken:
                    self.assertIsNone(initial['sprite'])
                    self.assertEqual(page.evaluate('runnerImages[0].naturalWidth'),0)
                else:
                    pose('idle')
                    alpha=page.evaluate("""() => runnerImages.filter(image=>image.src.includes('/runner/assets/shiba/')).map(image=>{
                      const canvas=document.createElement('canvas');canvas.width=canvas.height=512;
                      const context=canvas.getContext('2d');context.drawImage(image,0,0);
                      const pixels=context.getImageData(0,0,512,512).data;
                      let bottom=0;for(let i=3;i<pixels.length;i+=4)
                        if(pixels[i])bottom=Math.max(bottom,Math.floor((i-3)/4/512)+1);
                      return {name:image.src.split('/').pop().replace('.webp',''),corner:pixels[3],bottom};
                    })""")
                    self.assertEqual({frame['name'] for frame in alpha},set(SHIBA_FRAMES))
                    feet={'idle':465,'run_1':464,'run_2':465,'run_3':466,'run_4':464,
                          'jump_up':465,'jump_top':465,'jump_down':464,'land':466}
                    for frame in alpha:
                        self.assertEqual((frame['corner'],frame['bottom']),(0,feet[frame['name']]))
                self.assertAlmostEqual(initial['character']['x'],186,delta=.001)
                self.assertAlmostEqual(initial['character']['y'],427,delta=.001)
                self.toggle(page); page.evaluate('runnerClock.step(0)')
                pose('run_1')
                for frame in ('run_2','run_3','run_4','run_1'):
                    page.evaluate('runnerClock.advance(100,60)')
                    scene=pose(frame)
                    self.assertAlmostEqual(scene['character']['y'],
                        427-abs(math.sin(scene['now']/1000*math.pi*6))*4,
                        delta=.001)
                self.tap(page); page.evaluate('runnerClock.advance(225,60)')
                rising=pose('jump_up')
                self.assertAlmostEqual(rising['character']['y'],337,delta=.001)
                self.toggle(page)
                paused=pose('idle')
                self.assert_same_scene(rising,paused)
                self.assertEqual(paused['pending'],0)
                self.assertEqual(page.evaluate('runnerClock.advance(5000)'),0)
                self.assertEqual(self.snapshot(page)['image'],paused['image'])
                self.toggle(page); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                pose('jump_up')
                page.evaluate('runnerClock.advance(225,60)')
                jumped=pose('jump_top')
                self.assertAlmostEqual(jumped['character']['x'],186,delta=.001)
                self.assertAlmostEqual(jumped['character']['y'],307,delta=.001)
                if not broken:
                    self.assertAlmostEqual(jumped['sprite']['y'],
                      350-jumped['sprite']['height']*465/512,delta=.001)
                    self.assertEqual(jumped['sprite']['width'],initial['sprite']['width'])
                page.evaluate('runnerClock.advance(225,60)')
                self.assertAlmostEqual(pose('jump_down')['character']['y'],337,delta=.001)
                page.evaluate('runnerClock.advance(225,60)')
                landed=pose('land')
                self.assertAlmostEqual(landed['character']['y'],427,delta=4)
                page.evaluate('runnerClock.advance(100,60)')
                pose('land')
                page.evaluate('runnerClock.advance(20,60)')
                pose('run_3')
                self.assertEqual(jumped['pending'],1)
                self.assertEqual(page.locator('#runner-toggle').inner_text(),'一時停止')
                self.assert_isolated(page,errors,requests)

    def test_shiba_pose_timing_freezes_and_matches_at_60_and_120_hz(self):
        page,errors,requests=self.model_runner()
        outcomes=page.evaluate("""() => [60,120].map(hz=>{
          const {createRunnerState,updateRunner,startJump,characterPose,CHARACTER_SET}=runnerModel;
          const state=createRunnerState([]), poses=[characterPose(state)];
          function advance(seconds,target=state) {
            const count=Math.max(1,Math.round(seconds*hz));
            for(let i=0;i<count;i++)updateRunner(target,seconds/count);
          }
          state.mode='running'; poses.push(characterPose(state));
          for(let i=0;i<4;i++){advance(.1);poses.push(characterPose(state));}
          startJump(state);
          for(let i=0;i<4;i++){advance(.225);poses.push(characterPose(state));}
          const landed={time:state.animationTime,until:state.landingUntil,feet:state.feetY,support:state.supportId};
          advance(.1); poses.push(characterPose(state));
          state.mode='paused';const paused=JSON.stringify(state);
          advance(10);startJump(state);
          const frozen=JSON.stringify(state)===paused,pausedPose=characterPose(state);
          state.mode='running';const resumedPose=characterPose(state);
          const immediateJump=startJump(state),landingCleared=state.landingUntil===0;
          advance(.45);const secondPeak={pose:characterPose(state),height:state.jumpOriginY-state.feetY};
          const duration=createRunnerState([]);duration.mode='running';startJump(duration);
          advance(.9,duration);advance(.119,duration);const beforeEnd=characterPose(duration);
          advance(.002,duration);const afterEnd=characterPose(duration);
          state.mode='finished';const finishedPose=characterPose(state);
          const retry=createRunnerState([]);
          return {poses,landed,frozen,pausedPose,resumedPose,immediateJump,landingCleared,secondPeak,
            beforeEnd,afterEnd,finishedPose,config:{run:CHARACTER_SET.runFrameSeconds,
              landing:CHARACTER_SET.landingSeconds},retry:{pose:characterPose(retry),
              time:retry.animationTime,until:retry.landingUntil,feet:retry.feetY,support:retry.supportId,
              velocity:retry.velocityY,air:retry.airAction,
              distance:retry.distance,score:retry.score}};
        })""")
        expected=['idle','run_1','run_2','run_3','run_4','run_1',
                  'jump_up','jump_top','jump_down','land','land']
        for outcome in outcomes:
            self.assertEqual(outcome['poses'],expected)
            self.assertAlmostEqual(outcome['landed']['until']-outcome['landed']['time'],.12,delta=.000001)
            self.assertEqual((outcome['landed']['feet'],outcome['landed']['support']),(470,'ground'))
            self.assertTrue(outcome['frozen'])
            self.assertEqual((outcome['pausedPose'],outcome['resumedPose']),('idle','land'))
            self.assertTrue(outcome['immediateJump'])
            self.assertTrue(outcome['landingCleared'])
            self.assertEqual(outcome['secondPeak']['pose'],'jump_top')
            self.assertAlmostEqual(outcome['secondPeak']['height'],120,delta=.000001)
            self.assertEqual(outcome['beforeEnd'],'land')
            self.assertTrue(outcome['afterEnd'].startswith('run_'))
            self.assertEqual(outcome['finishedPose'],'idle')
            self.assertEqual(outcome['config'],{'run':.1,'landing':.12})
            self.assertEqual(outcome['retry'],{'pose':'idle','time':0,'until':0,
                'feet':470,'support':'ground','velocity':0,'air':None,'distance':0,'score':0})
        self.assert_isolated(page,errors,requests)

    def test_each_missing_shiba_frame_uses_old_shiba_without_changing_jump(self):
        times={'run_1':0,'run_2':100,'run_3':200,'run_4':300,
               'jump_up':225,'jump_top':450,'jump_down':675,'land':900}
        for frame in SHIBA_FRAMES:
            with self.subTest(frame=frame):
                page,errors,requests=self.manual_runner(broken_frames=(frame,))
                if frame != 'idle':
                    self.assertEqual(self.snapshot(page)['sprite']['pose'],'idle')
                    self.toggle(page);page.evaluate('runnerClock.step(0)')
                    if frame.startswith('jump_') or frame == 'land':
                        self.tap(page)
                    if times[frame]:
                        page.evaluate('ms=>runnerClock.advance(ms,60)',times[frame])
                scene=self.snapshot(page)
                self.assertEqual(scene['sprite']['pose'],'fallback')
                self.assertTrue(scene['sprite']['src'].endswith('/assets/plush/shiba.webp'))
                self.assertEqual((scene['sprite']['width'],scene['sprite']['height']),(100,100))
                if frame in ('jump_up','jump_down'):
                    self.assertAlmostEqual(scene['character']['y'],337,delta=.001)
                elif frame == 'jump_top':
                    self.assertAlmostEqual(scene['character']['y'],307,delta=.001)
                if frame == 'idle':
                    self.toggle(page);page.evaluate('runnerClock.step(0)')
                    self.assertEqual(self.snapshot(page)['sprite']['pose'],'run_1')
                self.assert_isolated(page,errors,requests)

    def test_delayed_shiba_frame_loads_while_hidden_without_advancing_or_auto_resuming(self):
        delayed={'run_2':None}
        page,errors,requests=self.open_runner(setup=MANUAL_FRAMES,delayed_frames=delayed)
        page.wait_for_function("""() => runnerImages.length>=11 &&
          runnerImages.filter(image=>!image.src.endsWith('/shiba/run_2.webp')).every(image=>image.complete)""",
          polling=10)
        page.evaluate('runnerClock.settle()');page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.settle()');page.evaluate('runnerClock.step(0)')
        self.assert_geometry(page)
        self.assertEqual(self.snapshot(page)['sprite']['pose'],'idle')
        self.toggle(page);page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(100,60)')
        running=self.snapshot(page)
        self.assertEqual(running['sprite']['pose'],'fallback')
        page.evaluate("""() => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
        }""")
        self.assertEqual(self.snapshot(page)['pending'],0)
        self.assertIsNotNone(delayed['run_2'])
        delayed['run_2'].fulfill(path=str(ROOT/'runner/assets/shiba/run_2.webp'))
        page.wait_for_function("runnerImages.find(image=>image.src.endsWith('/shiba/run_2.webp')).complete",
                               polling=10)
        self.assertEqual(self.snapshot(page)['pending'],0)
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'),0)
        page.evaluate("""() => {
          delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));
          window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
        }""")
        page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        restored=self.snapshot(page)
        self.assertEqual((restored['sprite']['pose'],restored['pending']),('idle',0))
        self.assert_same_scene(running,restored)
        self.assertEqual((restored['score'],restored['progress']),(running['score'],running['progress']))
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'再開')
        self.toggle(page);page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        self.assertEqual(self.snapshot(page)['sprite']['pose'],'run_2')
        page.evaluate('runnerClock.advance(100,60)')
        self.assertEqual(self.snapshot(page)['sprite']['pose'],'run_3')
        self.assert_isolated(page,errors,requests)

    def test_spike_rock_image_loads_with_alpha_and_stays_grounded_in_phone_tablet_layouts(self):
        for width,height in ((375,667),(390,844),(667,375),(844,390),(768,1024),(1024,768)):
            with self.subTest(width=width,height=height):
                page,errors,requests=self.manual_runner(width=width,height=height)
                self.toggle(page); page.evaluate('runnerClock.step(0)')
                page.evaluate('runnerClock.advance(3500,20)')
                before=self.snapshot(page)
                self.assertEqual(len(before['rocks']),1)
                rock=before['rocks'][0]
                self.assertTrue(rock['src'].endswith('/runner/assets/spike-rock.webp'))
                self.assertEqual((rock['naturalWidth'],rock['naturalHeight']),(640,466))
                self.assertEqual((rock['width'],rock['height']),(80,58.25))
                self.assertAlmostEqual(rock['width']/rock['height'],640/466,delta=.000001)
                self.assertAlmostEqual(rock['y']+rock['height']*464/466,470,delta=.000001)
                self.assertGreaterEqual(rock['x'],0)
                self.assertLessEqual(rock['x']+rock['width'],960)
                self.assertEqual(before['fallbackRocks'],0)
                page.evaluate('runnerClock.advance(250,20)')
                after=self.snapshot(page)['rocks'][0]
                self.assertAlmostEqual(rock['x']-after['x'],50,delta=.000001)
                self.assertAlmostEqual(rock['y'],after['y'],delta=.000001)
                self.assert_geometry(page)
                if width == 375:
                    alpha=page.evaluate("""() => {
                      const image=runnerImages.find(image=>image.src.endsWith('/runner/assets/spike-rock.webp'));
                      const canvas=document.createElement('canvas');
                      canvas.width=image.naturalWidth; canvas.height=image.naturalHeight;
                      const ctx=canvas.getContext('2d'); ctx.drawImage(image,0,0);
                      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
                      let left=canvas.width,top=canvas.height,right=-1,bottom=-1;
                      for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)
                        if(pixels[(y*canvas.width+x)*4+3]) {
                          left=Math.min(left,x);top=Math.min(top,y);
                          right=Math.max(right,x);bottom=Math.max(bottom,y);
                        }
                      return {corner:pixels[3],bounds:[left,top,right+1,bottom+1]};
                    }""")
                    self.assertEqual(alpha,{'corner':0,'bounds':[1,3,638,464]})
                self.assert_isolated(page,errors,requests)

    def test_missing_spike_rock_uses_fallback_and_preserves_motion_jump_collision_and_retry(self):
        page,errors,requests=self.manual_runner(broken_obstacle_image=True,probe=True)
        self.assertEqual(page.evaluate("runnerImages.find(image=>image.src.endsWith('/runner/assets/spike-rock.webp')).naturalWidth"),0)
        self.toggle(page); page.evaluate('runnerClock.step(0)')
        page.evaluate('runnerClock.advance(3500,20)')
        before=self.snapshot(page)
        self.assertEqual(before['rocks'],[])
        self.assertEqual(before['fallbackRocks'],1)
        self.assertIsNotNone(before['sprite'])
        page.locator('#runner-jump').tap()
        page.evaluate('runnerClock.advance(450,60)')
        airborne=self.snapshot(page)
        self.assertAlmostEqual(airborne['character']['y'],307,delta=.001)
        self.assertEqual(airborne['fallbackRocks'],1)
        self.assert_marker_advance(before,airborne,90)
        page.evaluate('runnerClock.advance(2000,60)')
        stopped=self.snapshot(page)
        self.assertEqual((stopped['score'],stopped['progress'],stopped['pending']),(10,16,0))
        self.assertEqual(page.locator('#runner-toggle').inner_text(),'つづける')
        self.toggle(page); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(3500,60)')
        stopped=self.snapshot(page)
        self.assertEqual(page.locator('#runner-result-title').inner_text(),'ゲームオーバー')
        self.assertEqual((page.evaluate(JUMP_PROBE)['velocityY'],page.evaluate(JUMP_PROBE)['supportId']),
                         (0,'ground'))
        self.assertEqual(page.evaluate('runnerClock.advance(10000)'),0)
        self.assertEqual(self.snapshot(page)['image'],stopped['image'])
        self.toggle(page); page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        restarted=self.snapshot(page)
        self.assertEqual((restarted['score'],restarted['progress'],restarted['rocks']),(0,0,[]))
        self.assertEqual(restarted['pending'],1)
        self.assertAlmostEqual(restarted['character']['y'],427,delta=.001)
        page.locator('#runner-jump').tap()
        page.evaluate('runnerClock.advance(450,60)')
        self.assertAlmostEqual(self.snapshot(page)['character']['y'],307,delta=.001)
        self.assert_isolated(page,errors,requests)


if __name__ == '__main__':
    unittest.main()
