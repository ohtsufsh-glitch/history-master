"""Issue #110 / #113 / #117: 操作前の実寸・全結果状態・親スクロール。独立context/合成DBのみ。"""
import json
import os
from pathlib import Path
import unittest

import runner_results_test as results
from runner_difficulty_cases import SOLUTIONS


SIZES = [(1180,820),(1024,768),(1366,1024),(1180,700),
         (820,1180),(390,844),(390,700),(844,390),(402,874),(375,667)]
# 描画は通常どおり行い、ゲーム時間だけbridge.advanceで進める。
# 実時間のrAFと合成ステップによる二重進行で攻略入力がずれることを防ぐ。
MANUAL_FRAME_TIME = """const nativeFrame=window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame=callback=>nativeFrame(()=>callback(0));"""
MEASURE = """()=>{
  const f=document.querySelector('#runner-frame-host iframe'),w=f.contentWindow,d=w.document;
  const box=e=>{
    const b=e.getBoundingClientRect();
    return {x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom,right:b.right,
      clientHeight:e.clientHeight,scrollHeight:e.scrollHeight};
  };
  const app=d.querySelector('.runner-app-formal'), style=w.getComputedStyle(app);
  const end=Math.max(...[...app.children].filter(e=>w.getComputedStyle(e).display!=='none'&&w.getComputedStyle(e).position!=='absolute').map(e=>e.getBoundingClientRect().bottom));
  const header=document.querySelector('main > header');
  return {parent:{width:innerWidth,height:innerHeight,scrollY,host:box(f.parentElement),iframe:box(f),
      headerBottom:getComputedStyle(header).position==='sticky'?box(header).bottom:0},
    child:{contentEnd:end,app:box(app),appHeight:style.height,appMinHeight:style.minHeight,paddingBottom:style.paddingBottom,visualHeight:w.visualViewport.height,parentVisualHeight:visualViewport.height,bottomBlank:w.innerHeight-Math.max(...['#runner-canvas','#runner-jump','#runner-toggle'].map(s=>d.querySelector(s).getBoundingClientRect().bottom)),width:w.innerWidth,height:w.innerHeight,scrollHeight:d.scrollingElement.scrollHeight,
      scrollWidth:d.scrollingElement.scrollWidth,scrollTop:d.scrollingElement.scrollTop,
      boxes:Object.fromEntries(['#runner-canvas','#runner-jump','#runner-toggle','#runner-result',
        '.runner-hud','#runner-status'].map(s=>[s,box(d.querySelector(s))]))}};
}"""


class RunnerLayoutTest(unittest.TestCase):
    setUpClass = classmethod(results.RunnerResultsTest.setUpClass.__func__)
    tearDownClass = classmethod(results.RunnerResultsTest.tearDownClass.__func__)
    def enter(self):
        results.RunnerResultsTest.enter(self)
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
        # #120: 入口はページ先頭。以降はユーザーがゲームへ移動した状態を検証する。
        self.page.evaluate("""()=>{
          const header=document.querySelector('main > header');
          const inset=getComputedStyle(header).position==='sticky'?header.getBoundingClientRect().height+8:0;
          scrollTo(0,scrollY+document.querySelector('#runner-frame-host').getBoundingClientRect().top-inset);
        }""")
    finish = results.RunnerResultsTest.finish

    def setUp(self):
        results.RunnerResultsTest.setUp(self)
        self.context.add_init_script(MANUAL_FRAME_TIME)
        self.reports = []

    def tearDown(self):
        if directory := os.environ.get('RUNNER_LAYOUT_REPORT_DIR'):
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            (path / (self._testMethodName + '.json')).write_text(
                json.dumps(self.reports, ensure_ascii=False, indent=2))
        results.RunnerResultsTest.tearDown(self)

    def settle(self):
        self.page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')

    def measure(self, state, initial=None, result=False):
        # Locatorのclick/tap/scroll_into_viewより先に測る。親座標も併せて検証する。
        self.settle()
        m = self.page.evaluate(MEASURE)
        self.reports.append(dict(state=state, **m))
        if self._testMethodName == 'test_all_sizes_all_states_without_inner_scroll' and (m['parent']['width'],m['parent']['height']) in [(390,844),(390,700)] and state in ['running','clear']:
            if directory := os.environ.get('RUNNER_LAYOUT_REPORT_DIR'):
                Path(directory).mkdir(parents=True, exist_ok=True)
                self.page.screenshot(path=str(Path(directory) / (f'{m["parent"]["width"]}x{m["parent"]["height"]}-{state}.png')))
        c, p = m['child'], m['parent']
        self.assertEqual(c['scrollTop'], 0, state)
        self.assertLessEqual(c['scrollHeight'], c['height'] + 1, state)
        self.assertLessEqual(c['scrollWidth'], c['width'] + 1, state)
        selectors = ['#runner-canvas','#runner-jump','#runner-toggle','.runner-hud']
        if c['boxes']['#runner-status']['height']:
            selectors.append('#runner-status')
        if result:
            selectors.append('#runner-result')
        for s in selectors:
            b = c['boxes'][s]
            self.assertGreater(b['width'], 0, (state,s))
            self.assertGreaterEqual(b['x'], -1, (state,s))
            self.assertLessEqual(b['right'], c['width'] + 1, (state,s))
            self.assertGreaterEqual(b['y'], -1, (state,s))
            self.assertLessEqual(b['bottom'], c['height'] + 1, (state,s))
            self.assertGreaterEqual(p['iframe']['y'] + b['y'], -1, (state,s))
            self.assertGreaterEqual(p['iframe']['y'] + b['y'], p['headerBottom']-1, (state,s,'header overlap'))
            self.assertLessEqual(p['iframe']['y'] + b['bottom'], p['height'] + 1, (state,s))
        for s in ['#runner-jump','#runner-toggle']:
            self.assertGreaterEqual(c['boxes'][s]['height'], 44)
            self.assertGreaterEqual(c['boxes'][s]['width'], 44)
        canvas, jump = c['boxes']['#runner-canvas'], c['boxes']['#runner-jump']
        self.assertAlmostEqual(canvas['width']/canvas['height'], 16/9, delta=.01)
        if (p['width'], p['height']) in SIZES[:4]:
            toggle = c['boxes']['#runner-toggle']
            self.assertGreater(canvas['width'], 527)
            for b in [jump, toggle]:
                self.assertAlmostEqual(b['x']+b['width']/2, canvas['x']+canvas['width']/2, delta=1)
                self.assertGreaterEqual(b['height'], 48)
            self.assertGreaterEqual(jump['y'], canvas['bottom'])
            self.assertGreaterEqual(jump['height'], 64)
            self.assertGreaterEqual(toggle['y'], jump['bottom']+16)
        if p['width'] in [375,390,402]:
            # #117: 状態通知・下paddingを収め、親の余剰高を戻さない。
            self.assertLessEqual(c['height'], 520)
            self.assertLessEqual(c['contentEnd'] + float(c['paddingBottom'].removesuffix('px')), c['height'] + 1)
            self.assertAlmostEqual(jump['y']-canvas['bottom'], 12, delta=1)
        if result:
            panel = c['boxes']['#runner-result']
            self.assertLessEqual(panel['scrollHeight'], panel['clientHeight'] + 1)
        if initial:
            self.assertAlmostEqual(p['iframe']['height'], initial['parent']['iframe']['height'], delta=1)
            self.assertAlmostEqual(p['scrollY'], initial['parent']['scrollY'], delta=1)
            for s in ['#runner-canvas','#runner-jump','#runner-toggle']:
                for key in ['x','y','width','height']:
                    self.assertAlmostEqual(c['boxes'][s][key], initial['child']['boxes'][s][key], delta=1, msg=(state,s,key))
        return m

    def tap(self, frame, text):
        # タップ直前にも可視性とscrollTop=0を検証。自動スクロール後の見かけの合格を防ぐ。
        frame.locator('#runner-toggle').filter(has_text=text).wait_for()
        self.measure('before tap: ' + text)
        if text in ['ゲーム開始','再挑戦']:
            self.page.once('dialog', lambda d:d.accept())
        frame.locator('#runner-toggle').tap()
        expected = 'paused' if text == '一時停止' else 'running'
        self.page.wait_for_function('mode=>formalRunner.session?.view.state.mode===mode', arg=expected)

    def test_all_sizes_all_states_without_inner_scroll(self):
        self.context.close()
        self.context = self.browser.new_context(has_touch=True)
        self.context.add_init_script(MANUAL_FRAME_TIME)
        self.page = self.context.new_page()
        self.page.goto(self.url)
        self.page.wait_for_function('appReady')
        # 共通セットアップの公開可能な合成fixtureだけをこのcontextにも用意する。
        from plush_test import FIXTURE_HELPERS
        self.page.evaluate(FIXTURE_HELPERS)
        self.page.evaluate("""async()=>{
          window.m=await loadRunnerModel();
          window.install=async()=>{
            const d=plushFixture([],'student');await plushInstall(d);
          };
        }""")
        for width,height in SIZES:
            with self.subTest(width=width,height=height):
                self.page.evaluate('async()=>{await navigateHome();await install();}')
                self.page.set_viewport_size(dict(width=width,height=height))
                self.enter()
                frame = self.page.frame_locator('iframe')
                frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
                initial = self.measure('ready')
                self.assertEqual(frame.locator('.runner-help').count(), 0)
                self.assertIn('タップするとジャンプ', frame.locator('#runner-canvas').get_attribute('aria-label'))
                if width==844:
                    self.assertLessEqual(initial['child']['boxes']['#runner-canvas']['right'],
                                         initial['child']['boxes']['#runner-jump']['x'])
                self.tap(frame, 'ゲーム開始')
                frame.locator('#runner-toggle').filter(has_text='一時停止').wait_for()
                self.measure('running', initial)
                frame.locator('#runner-jump').tap()
                self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
                self.tap(frame, '一時停止')
                frame.locator('#runner-toggle').filter(has_text='再開').wait_for()
                self.measure('paused', initial)
                self.tap(frame, '再開')
                self.measure('resumed', initial)
                for _ in range(2):
                    self.tap(frame, '一時停止')
                    self.measure('repeated pause', initial)
                    self.tap(frame, '再開')
                    self.measure('repeated resume', initial)
                self.finish()
                frame.locator('#runner-result-title').filter(has_text='ゲームオーバー').wait_for()
                self.measure('gameover', initial, result=True)
                self.tap(frame, '再挑戦')
                self.measure('retry', initial)
                # 実際にクリアし、最終保存を保留。新記録・解放が先に出ないことも確認。
                self.page.evaluate("""times=>{
                  window.originalLayoutSave=saveRunnerState;
                  saveRunnerState=async(...a)=>{
                    if(a[3].mode==='finished')await new Promise(r=>window.releaseLayoutSave=r);
                    return originalLayoutSave(...a);
                  };
                  window.layoutFinishing=(async()=>{
                    const c=formalRunner.session;let n=0;
                    while(c.view.state.mode==='running'){
                      if(n<times.length&&c.view.state.elapsed+1e-8>=times[n]){await c.jump();n++;}
                      await formalRunner.bridge.advance(1/60);
                    }
                  })();
                }""", SOLUTIONS['S01']['perfect'])
                self.page.wait_for_function('typeof releaseLayoutSave === "function"')
                self.page.evaluate("document.querySelector('iframe').contentWindow.refreshFormalRunner()")
                frame.locator('#runner-result-title').filter(has_text='保存中').wait_for()
                self.measure('pending clear', initial, result=True)
                self.assertEqual(frame.locator('#runner-result-record').inner_text(), '')
                self.assertEqual(frame.locator('#runner-result-unlock').inner_text(), '')
                self.assertTrue(frame.locator('#runner-toggle').is_disabled())
                self.page.evaluate('async()=>{saveRunnerState=originalLayoutSave;releaseLayoutSave();await layoutFinishing;delete window.releaseLayoutSave;}')
                frame.locator('#runner-result-title').filter(has_text='クリア！').wait_for()
                self.measure('clear', initial, result=True)
                self.assertIn('S02', frame.locator('#runner-result-unlock').inner_text())
                self.tap(frame, '再挑戦')
                self.page.evaluate("""async()=>{
                  const original=saveRunnerState;
                  saveRunnerState=async(...a)=>{
                    if(a[3].mode==='finished')throw new Error('synthetic storage full');
                    return original(...a);
                  };
                  try{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05);}
                  catch{}finally{saveRunnerState=original;}
                  document.querySelector('iframe').contentWindow.refreshFormalRunner();
                }""")
                frame.locator('#runner-result-title').filter(has_text='まだ保存').wait_for()
                self.measure('failed finish', initial, result=True)
                self.assertEqual(frame.locator('#runner-result-record').inner_text(), '')
                self.assertEqual(frame.locator('#runner-result-unlock').inner_text(), '')
                self.tap(frame, '最後の保存から再開（無料）')
                frame.locator('#runner-toggle').filter(has_text='一時停止').wait_for()
                self.measure('free resume', initial)
                self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).map(s=>s.amount)"), [30,30,30])
                print(f'{width}x{height}: 10 states, iframe/document={initial["child"]["height"]}, scrollTop=0', flush=True)

    def test_parent_scroll_and_resize_do_not_rewind(self):
        self.page.set_viewport_size(dict(width=1180,height=700))
        self.enter()
        self.page.frame_locator('iframe').locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
        self.measure('ready')
        # 通常のwheel入力をiframeのHUD上に送り、親の選択欄へ自然に移れることを確認。
        p = self.page.evaluate(MEASURE)['parent']['iframe']
        self.page.mouse.move(p['x']+p['width']-40, p['y']+60)
        self.page.mouse.wheel(0, 550)
        self.page.wait_for_function('scrollY>550')
        self.assertEqual(self.page.frames[-1].evaluate('document.scrollingElement.scrollTop'), 0)
        self.assertTrue(self.page.locator('#runner-choices').evaluate('e=>e.getBoundingClientRect().top<innerHeight'))
        self.page.locator('#formal-character-cards').scroll_into_view_if_needed()
        card_before = self.page.locator('#formal-character-cards').evaluate('e=>e.getBoundingClientRect().top')
        self.page.evaluate("window.originalFrame=formalRunner.frame")
        self.page.set_viewport_size(dict(width=1180,height=820))
        self.settle()
        # 実リサイズではブラウザのscroll anchoringでscrollY自体は変わる。
        # 同じ選択欄が同じ位置に留まり、復帰イベントでは巻き戻さないことを確認する。
        self.assertAlmostEqual(self.page.locator('#formal-character-cards').evaluate('e=>e.getBoundingClientRect().top'), card_before, delta=1)
        before = self.page.evaluate('scrollY')
        self.page.evaluate("""async()=>{
          window.dispatchEvent(new Event('resize'));
          window.dispatchEvent(new Event('orientationchange'));
          window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
          window.dispatchEvent(new Event('focus'));
          await formalRunner.refresh();
        }""")
        self.settle()
        self.assertAlmostEqual(self.page.evaluate('scrollY'), before, delta=1)
        self.assertTrue(self.page.evaluate('originalFrame===formalRunner.frame'))

    def test_split_view_switches_with_available_width(self):
        for width,height in [(700,900),(900,700),(1024,768)]:
            with self.subTest(width=width,height=height):
                self.page.evaluate('async()=>{await navigateHome();await install();}')
                self.page.set_viewport_size(dict(width=width,height=height))
                self.enter()
                self.page.frame_locator('iframe').locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
                m = self.measure('split ready')
                c = m['child']['boxes']['#runner-canvas']
                j = m['child']['boxes']['#runner-jump']
                self.assertAlmostEqual(c['x']+c['width']/2, j['x']+j['width']/2, delta=1)
                self.assertGreaterEqual(j['y'], c['bottom'])

    def test_demo_preview_help_removed(self):
        for suffix in ['runner/', 'runner/?stagePreview=1']:
            page = self.context.new_page()
            page.goto(self.url.rsplit('/',1)[0]+'/'+suffix)
            page.locator('#runner-toggle:enabled').wait_for()
            self.assertEqual(page.locator('.runner-help').count(), 0)
            self.assertNotIn('ジャンプボタンか画面タップ', page.locator('body').inner_text())
            self.assertIn('タップするとジャンプ', page.locator('#runner-canvas').get_attribute('aria-label'))
            page.close()

    def test_enlarged_text_and_tiny_viewport_do_not_clip_results(self):
        for width,height in [(1180,700),(844,390),(390,300),(390,844),(390,700),(402,874),(375,667)]:
            with self.subTest(width=width,height=height):
                self.page.evaluate('async()=>{await navigateHome();await install();}')
                self.page.set_viewport_size(dict(width=width,height=height))
                self.enter()
                frame = self.page.frame_locator('iframe')
                frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
                self.page.once('dialog',lambda d:d.accept())
                frame.locator('#runner-toggle').click()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
                self.finish(clear=True)
                frame.locator('#runner-result-unlock').filter(has_text='S02').wait_for()
                self.page.frames[-1].evaluate("document.documentElement.style.fontSize='200%'")
                self.settle()
                m = self.page.evaluate(MEASURE)
                self.reports.append(dict(state='200% clear', **m))
                self.assertLessEqual(m['child']['scrollWidth'], m['child']['width']+1)
                panel = m['child']['boxes']['#runner-result']
                self.assertLessEqual(panel['scrollHeight'], panel['clientHeight']+1)
                # 拡大・極小画面はdocumentでスクロール可。切り捨てず各情報と操作へ到達可能。
                for selector in ['#runner-result-title','#runner-result-score',
                                 '#runner-result-record','#runner-result-unlock','#runner-toggle']:
                    e = frame.locator(selector)
                    e.scroll_into_view_if_needed()
                    self.assertTrue(e.evaluate("""e=>{
                      const b=e.getBoundingClientRect();
                      return b.top>=-1&&b.bottom<=innerHeight+1;
                    }"""))
                self.assertTrue(frame.locator('#runner-toggle').is_enabled())
