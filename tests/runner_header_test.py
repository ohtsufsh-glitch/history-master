"""#119/#118: 合成DBだけで残高の正本・非同期競合・タイトルと実座標を検証。"""
import json
import os
from pathlib import Path
import unittest
import runner_layout_test as layout
from runner_layout_test import SIZES, MEASURE


class RunnerHeaderTest(unittest.TestCase):
    setUpClass = classmethod(layout.RunnerLayoutTest.setUpClass.__func__)
    tearDownClass = classmethod(layout.RunnerLayoutTest.tearDownClass.__func__)
    setUp = layout.RunnerLayoutTest.setUp
    def tearDown(self):
        self.context.close()
    enter = layout.RunnerLayoutTest.enter
    settle = layout.RunnerLayoutTest.settle

    def balance(self, text):
        self.page.wait_for_function('t=>document.querySelector("#runner-balance").textContent===t', arg=text)
        self.assertEqual(self.page.locator('#runner-balance').count(), 1)
        self.assertEqual(self.page.frame_locator('iframe').locator('#runner-balance, #runner-balance-status, .arcade-balance').count(), 0)

    def test_saved_balances_cancel_purchase_resume_retry_and_profiles(self):
        for amount in [0,29,30,100]:
            self.page.evaluate('async n=>{await navigateHome();await install(n);}',amount)
            self.enter();self.balance(f'{amount}枚')
        self.page.once('dialog',lambda d:d.dismiss())
        self.page.evaluate('formalRunner.bridge.resume()');self.balance('100枚')
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),0)
        self.page.once('dialog',lambda d:d.accept())
        self.page.evaluate('formalRunner.bridge.resume()');self.balance('70枚')
        self.page.evaluate('async()=>{await formalRunner.bridge.pause();await formalRunner.bridge.resume();}')
        self.balance('70枚')
        self.page.evaluate("async()=>{await navigateHome();await navigate('runner');}")
        self.page.evaluate('formalRunner.bridge.resume()');self.balance('70枚')
        self.page.evaluate("navigate('runner','test')");self.balance('∞（無料）')
        self.page.evaluate('formalRunner.bridge.resume()');self.balance('∞（無料）')
        self.page.evaluate("navigate('runner','student')");self.balance('70枚')
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).map(s=>s.amount).sort((a,b)=>a-b)"),[0,30])

    def test_entry_read_failure_does_not_show_old_balance(self):
        self.page.evaluate("""async()=>{
          window.entryLobby=runnerLobbyData;
          runnerLobbyData=async()=>{throw new Error('synthetic entry read failure');};
          await navigate('runner').catch(()=>{});
        }""")
        self.assertEqual(self.page.locator('#runner-balance').inner_text(),'確認できません')
        self.page.evaluate('async()=>{runnerLobbyData=entryLobby;await renderRunnerLobby();}')
        self.balance('30枚')

    def test_pending_error_latest_request_and_profile_generation(self):
        self.enter();self.balance('30枚')
        self.page.evaluate('''()=>{
          window.originalLobby=runnerLobbyData;
          runnerLobbyData=async who=>{const d=await originalLobby(who);await new Promise(r=>window.releaseRead=r);return d;};
          window.pendingRead=formalRunner.refresh();
        }''')
        self.page.wait_for_function('!!window.releaseRead');self.balance('確認中…')
        self.page.evaluate('''async()=>{
          await runnerTransaction(['reviewEvents'],tx=>tx.objectStore('reviewEvents').put({key:'extra',profile:'student',amount:70}));
          runnerLobbyData=originalLobby;
          formalRunner.refresh();releaseRead();await pendingRead;
        }''');self.balance('100枚')
        self.page.evaluate('''async()=>{
          runnerLobbyData=async()=>{throw new Error('synthetic read error');};
          await formalRunner.refresh().catch(()=>{});
        }''');self.balance('確認できません')
        self.page.evaluate('''()=>{
          runnerLobbyData=async who=>{const d=await originalLobby(who);await new Promise(r=>window.releaseOldProfile=r);return d;};
          window.oldProfileRead=formalRunner.refresh();
        }''');self.page.wait_for_function('!!window.releaseOldProfile')
        self.page.evaluate("async()=>{runnerLobbyData=originalLobby;await navigate('runner','test');releaseOldProfile();await oldProfileRead;}")
        self.balance('∞（無料）')

    def test_failed_finish_free_recovery_and_paid_retry(self):
        self.page.evaluate('install(100)');self.enter()
        self.page.once('dialog',lambda d:d.accept())
        self.page.evaluate('formalRunner.bridge.resume()');self.balance('70枚')
        self.page.evaluate("""async()=>{
          const original=saveRunnerState;
          saveRunnerState=async(...a)=>{if(a[3].mode==='finished')throw new Error('synthetic full');return original(...a);};
          try{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05);}
          catch{}finally{saveRunnerState=original;}
        }""");self.balance('70枚')
        self.assertIsNotNone(self.page.evaluate('formalRunner.session.view.error'))
        self.page.evaluate('formalRunner.bridge.resume()');self.balance('70枚')
        self.page.evaluate("async()=>{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05);}")
        self.balance('70枚')
        self.page.once('dialog',lambda d:d.accept())
        self.page.evaluate('formalRunner.bridge.resume()');self.balance('40枚')
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).map(s=>s.amount)"),[30,30])

    def test_other_tab_focus_visibility_storage_and_catcher(self):
        self.enter()
        other=self.context.new_page();other.goto(self.url);other.wait_for_function('appReady')
        for event,n in [('focus',10),('visibilitychange',20),('storage',30),('pageshow',40)]:
            other.evaluate("n=>runnerTransaction(['reviewEvents'],tx=>tx.objectStore('reviewEvents').put({key:'other-tab',profile:'student',amount:n}))",n)
            self.page.evaluate("name=>{if(name==='pageshow')dispatchEvent(new PageTransitionEvent(name,{persisted:true}));else (name==='visibilitychange'?document:window).dispatchEvent(new Event(name));}",event)
            self.balance(f'{30+n}枚')
        self.page.evaluate("navigate('arcade')")
        self.page.locator('#arcade-balance').filter(has_text='70枚').wait_for()
        self.assertEqual(self.page.locator('.arcade-balance').last.evaluate('e=>getComputedStyle(e).backgroundColor'),'rgb(255, 243, 206)')

    def test_sizes_initial_and_playing_coordinates_and_title(self):
        report=[]
        for width,height in SIZES+[(700,900),(500,700)]:
            self.page.evaluate('async()=>{await navigateHome();await install(100);}');self.page.set_viewport_size(dict(width=width,height=height))
            self.page.evaluate("document.querySelector('#open-runner').click()")
            self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
            self.balance('100枚')
            self.assertEqual(self.page.evaluate('scrollY'),0)
            b=self.page.locator('#runner-balance').bounding_box()
            self.assertGreaterEqual(b['y'],0);self.assertLessEqual(b['y']+b['height'],height)
            initial=self.page.evaluate(MEASURE)
            directory=os.environ.get('RUNNER_HEADER_REPORT_DIR')
            if directory:
                Path(directory).mkdir(parents=True,exist_ok=True)
                self.page.screenshot(path=f'{directory}/{width}x{height}-entry.png')
            self.page.evaluate('''()=>{const h=document.querySelector('main > header');
              const inset=getComputedStyle(h).position==='sticky'?h.getBoundingClientRect().height+8:0;
              scrollTo(0,scrollY+document.querySelector('#runner-frame-host').getBoundingClientRect().top-inset);}''')
            frame=self.page.frames[-1]
            child=frame.evaluate('''()=>{
              const box=s=>{const b=document.querySelector(s).getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom};};
              return {header:box('.runner-header'),mode:box('#runner-mode'),title:box('#runner-title'),name:document.querySelector('main').getAttribute('aria-labelledby')};
            }''')
            self.assertEqual(child['name'],'runner-title');self.assertEqual(child['title']['width'],1)
            self.assertIn('main "わくわくランナー"',frame.locator('main').aria_snapshot())
            before=layout.RunnerLayoutTest.measure(self, 'ready')
            self.assertEqual(frame.locator('#runner-mode').inner_text(),'開始前')
            self.assertLessEqual(child['mode']['bottom'],before['child']['boxes']['#runner-canvas']['y'])
            # 長い失敗文言・読込中・保存済みを切り替えてもゲーム/操作は動かない。
            for text in ['確認中…','確認できません','∞（無料）','100枚']:
                self.page.evaluate('showRunnerBalance',text)
                after=self.page.evaluate(MEASURE)
                self.assertEqual(after['child']['scrollHeight'],after['child']['height'])
                for s in ['#runner-canvas','#runner-jump','#runner-toggle']:
                    self.assertEqual(before['child']['boxes'][s],after['child']['boxes'][s])
            self.page.evaluate('formalRunner.refresh()');self.balance('100枚')
            self.page.once('dialog',lambda d:d.accept())
            self.page.evaluate('formalRunner.bridge.resume()');self.balance('70枚')
            self.assertEqual(self.page.evaluate('formalRunner.bridge.view.state.mode'),'running')
            self.assertEqual(frame.locator('#runner-mode').inner_text(),'走行中')
            layout.RunnerLayoutTest.measure(self, 'running', before)
            if directory:self.page.screenshot(path=f'{directory}/{width}x{height}-play.png')
            report.append(dict(size=[width,height],initial=initial,playing=before,header=child,parentBalance=b))
        if directory:Path(directory,'coordinates.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))

    def test_demo_and_preview_keep_visible_title(self):
        for suffix in ['', '?stagePreview=1']:
            self.page.goto(self.url.replace('index.html','runner/')+suffix)
            self.page.locator('#runner-toggle:enabled').wait_for()
            self.assertGreater(self.page.locator('#runner-title').bounding_box()['width'],1)
            self.assertEqual(self.page.locator('#runner-balance-status, #runner-balance').count(), 0)
