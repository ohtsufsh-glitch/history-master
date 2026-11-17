"""Issue #82: カード操作を独立ブラウザDB・合成データで検証。"""
import unittest
from runner_results_test import RunnerResultsTest


class RunnerSelectionTest(unittest.TestCase):
    setUpClass = classmethod(RunnerResultsTest.setUpClass.__func__)
    tearDownClass = classmethod(RunnerResultsTest.tearDownClass.__func__)
    setUp = RunnerResultsTest.setUp
    tearDown = RunnerResultsTest.tearDown
    enter = RunnerResultsTest.enter
    start = RunnerResultsTest.start
    finish = RunnerResultsTest.finish

    def card(self, kind, id):
        return self.page.locator(f'#formal-{kind}-cards [data-choice="{id}"]')

    def test_normal_cards_abilities_hearts_and_keyboard(self):
        self.enter()
        cases=[('shiba','しば犬','中','中',2),('sloth','なまけもの','低','中',2),
               ('goldfish','金魚','中','高',2),('salamander','オオサンショウウオ','高','低',3)]
        for id,name,speed,jump,hearts in cases:
            card=self.card('character',id)
            card.focus();card.press('Enter')
            self.assertEqual(card.get_attribute('aria-pressed'),'true')
            self.assertEqual(self.page.locator('#formal-character-cards [aria-pressed="true"]').count(),1)
            self.assertIn(id+'.webp',card.locator('img').get_attribute('src'))
            info=self.page.locator('#formal-character-info').inner_text()
            for text in [name,f'走力：{speed}',f'ジャンプ：{jump}','♥'*hearts]:self.assertIn(text,info)
            self.assertNotIn('残機',self.page.locator('#runner').inner_text())
            self.assertEqual(self.page.evaluate('formalRunner.bridge.view.state.initialLives'),hearts)
            self.assertEqual(self.page.locator('#runner-character-bests .is-selected .runner-record-name').inner_text(),name)
            frame=self.page.frame_locator('iframe')
            self.assertIn(f'あと{hearts}個',frame.locator('#runner-lives').get_attribute('aria-label'))
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),0)

    def test_secret_lock_acquired_refresh_profile_and_reset(self):
        self.enter()
        self.assertTrue(self.card('character','secret-locked').is_disabled())
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        self.assertEqual(self.page.locator('#runner-choices img[src*="secret_yuniko"]').count(),0)
        self.page.evaluate("""async()=>{
          // 抽選解放の35種類だけでは使用不可。
          const ids=PLUSH_IDS.slice(0,35);
          await replaceAllStores(plushFixture(ids,'student'));await formalRunner.refresh();
        }""")
        self.assertTrue(self.card('character','secret-locked').is_disabled())
        self.page.evaluate("""async()=>{
          await replaceAllStores(plushFixture(['secret_yuniko'],'student'));await formalRunner.refresh();
        }""")
        self.card('character','secret_yuniko').click()
        self.assertIn('走力：中 ／ ジャンプ：中 ／ ハート：♥♥♥',self.page.locator('#formal-character-info').inner_text())
        self.assertIn('追加ジャンプ1回',self.page.locator('#formal-character-info').inner_text())
        self.page.evaluate("async()=>{await navigate('runner','test');}")
        self.assertTrue(self.card('character','secret-locked').is_disabled())
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        self.page.evaluate("async()=>{await navigate('runner','student');await performReset({student:true});await formalRunner.refresh();}")
        self.assertTrue(self.card('character','secret-locked').is_disabled())

    def test_all_stages_unlock_and_records_refresh_without_charge(self):
        self.enter()
        self.assertEqual(self.page.locator('#formal-stage-cards button:disabled').count(),5)
        self.assertIn('前のステージ',self.card('stage','S02').inner_text())
        self.assertFalse(self.page.evaluate("formalRunner.select('S06','shiba')"))
        self.page.evaluate("""async()=>{
          const at='2020-01-01T00:00:00.000Z';
          await runnerTransaction(['runnerPlays'],tx=>{
            for(let i=1;i<=5;i++)tx.objectStore('runnerPlays').put({id:'clear'+i,profile:'student',stageId:'S0'+i,
              characterId:'shiba',status:'finished',score:0,result:{reason:'clear',at}});
            tx.objectStore('runnerPlays').put({id:'best',profile:'student',stageId:'S06',characterId:'goldfish',status:'finished',score:100,result:{reason:'gameover',at}});
          });await formalRunner.refresh();
        }""")
        for i in range(1,7):
            card=self.card('stage',f'S0{i}');card.scroll_into_view_if_needed()
            box=card.bounding_box()
            cdp=self.page.context.new_cdp_session(self.page)
            cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            self.assertEqual(card.get_attribute('aria-pressed'),'true')
            self.assertNotIn('前のステージ',card.inner_text())
            self.assertIn('100点' if i==6 else '0点',self.page.locator('#runner-stage-best').inner_text())
        self.card('character','goldfish').click()
        self.assertEqual(self.page.locator('#runner-character-bests .is-selected .runner-record-name').inner_text(),'金魚')
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),0)

    def test_running_paused_finished_and_pending_selection(self):
        frame=self.start()
        self.assertTrue(self.card('character','goldfish').is_disabled())
        frame.locator('#runner-toggle').click()
        self.assertTrue(self.card('stage','S01').is_disabled())
        self.assertFalse(self.page.evaluate("formalRunner.select('S01','goldfish')"))
        self.page.locator('#runner-home').click();self.enter()
        self.assertTrue(self.card('character','goldfish').is_disabled())
        frame.locator('#runner-toggle').click()
        self.page.evaluate("""()=>{
          window.originalSave=saveRunnerState;
          saveRunnerState=async(...args)=>{if(args[3].mode==='finished')await new Promise(r=>window.releaseFinish=r);return originalSave(...args);};
          window.finishing=(async()=>{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05);})();
        }""")
        self.page.wait_for_function('typeof releaseFinish === "function"')
        self.assertTrue(self.card('character','goldfish').is_disabled())
        self.page.evaluate('async()=>{saveRunnerState=originalSave;releaseFinish();await finishing;}')
        self.card('character','goldfish').click()
        self.assertEqual(self.page.evaluate('formalRunner.bridge.view.state.characterId'),'goldfish')
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),1)

    def test_touch_sizes_and_focus_survives_refresh(self):
        self.enter()
        for w,h in [(390,844),(844,390),(820,1180)]:
            self.page.set_viewport_size(dict(width=w,height=h))
            card=self.card('character','salamander');card.scroll_into_view_if_needed()
            box=card.bounding_box()
            cdp=self.page.context.new_cdp_session(self.page)
            cdp.send('Emulation.setTouchEmulationEnabled',{'enabled':True})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            self.assertEqual(card.get_attribute('aria-pressed'),'true')
            self.assertEqual(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'),True)
            for rect in self.page.locator('.runner-choice-card').evaluate_all('(bs)=>bs.map(b=>{const r=b.getBoundingClientRect();return [r.width,r.height]})'):
                self.assertGreaterEqual(min(rect),44)
            card.focus();self.page.evaluate('async()=>{await formalRunner.refresh();}')
            self.assertEqual(card.evaluate('(b)=>document.activeElement===b'),True)
            self.assertTrue(self.page.evaluate("document.querySelector('#runner-choices').getBoundingClientRect().top>=document.querySelector('iframe').getBoundingClientRect().bottom"))


del RunnerResultsTest
