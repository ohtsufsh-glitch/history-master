"""段階②の独立Canvas画面。HTTPと一時Chromiumのみを使用する。

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
        self.assertTrue(actual['button']['disabled'])
        self.assertGreaterEqual(actual['button']['width'], 44)
        self.assertGreaterEqual(actual['button']['height'], 44)
        for text in ('ランナーゲーム', '0点', '30秒', '開発中'):
            self.assertIn(text, actual['text'])
        return actual

    def test_http_static_scene_and_phone_tablet_layouts(self):
        sizes = ((375, 667, 1), (390, 844, 3), (667, 375, 2), (844, 390, 3),
                 (768, 1024, 2), (1024, 768, 2), (1024, 1366, 2), (1366, 1024, 2))
        for width, height, dpr in sizes:
            with self.subTest(width=width, height=height, dpr=dpr):
                page, errors, requests = self.open_runner(width, height, dpr)
                self.assert_geometry(page)
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


if __name__ == '__main__':
    unittest.main()
