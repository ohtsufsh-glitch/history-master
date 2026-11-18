"""#137② / #138: テスト用選択権限とホーム表示。合成データのみ。"""
import os
from pathlib import Path
import unittest
from runner_session_test import RunnerSessionTest


class RunnerTestModeTest(unittest.TestCase):
    setUpClass = classmethod(RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(RunnerSessionTest.tearDownClass.__func__)
    setUp = RunnerSessionTest.setUp
    tearDown = RunnerSessionTest.tearDown

    def enter(self, who):
        self.page.evaluate("who=>navigate('runner',who)", who)
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()

    def test_all_stages_select_start_finish_and_reset_without_fake_records(self):
        self.enter('test')
        self.assertEqual(self.page.locator('#formal-stage option:disabled').count(), 0)
        self.assertNotIn('🔒', self.page.locator('#formal-stage-cards').inner_text())
        self.assertTrue(self.page.locator('#formal-stage-lock-help').is_hidden())
        self.assertEqual(self.page.evaluate("async()=>(await readAll('runnerPlays')).length"), 0)
        for stage in ['S01','S02','S03','S04','S05','S06']:
            with self.subTest(stage=stage):
                self.page.locator(f'#formal-stage-cards [data-choice="{stage}"]').click()
                self.page.frame_locator('iframe').locator('#runner-toggle').click()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
                self.assertEqual(self.page.evaluate('[formalRunner.session.view.savedPlay.stageId,formalRunner.session.view.savedPlay.profile]'), [stage,'test'])
                self.page.evaluate("""async()=>{
                  while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05);
                }""")
                self.page.frame_locator('iframe').locator('#runner-toggle').filter(has_text='再挑戦').wait_for()
                self.assertEqual(self.page.locator('#formal-stage option:disabled').count(), 0)
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).map(s=>s.amount)"), [0]*6)
        self.assertEqual(self.page.evaluate("async()=>{const d=await runnerLobbyData('test');return [d.summary.unlockedStageIds,d.records.filter(p=>p.result.reason==='clear').length];}"), [['S01'],0])
        self.assertTrue(self.page.evaluate("rejected(()=>buy({profile:'test',characterId:'secret_yuniko'}))"))
        self.page.evaluate("async()=>{await performReset({test:true});await renderRunnerLobby();}")
        self.assertEqual(self.page.locator('#formal-stage option:disabled').count(), 0)
        self.assertEqual(self.page.evaluate("async()=>(await readAll('runnerPlays')).length"), 0)

    def test_student_locks_payment_profile_isolation_and_active_priority(self):
        self.enter('student')
        self.assertEqual(self.page.locator('#formal-stage option:disabled').count(), 5)
        self.assertTrue(self.page.locator('#formal-stage-lock-help').is_visible())
        self.assertTrue(self.page.evaluate("""async()=>{
          for(const stageId of RUNNER_STAGE_IDS.slice(1))if(!await rejected(()=>buy({stageId})))return false;
          return await rejected(()=>buy({characterId:'secret_yuniko'}));
        }"""))
        self.assertEqual(self.page.evaluate("""async()=>{
          const p=await buy({profile:'test',stageId:'S06'});
          const again=await buy({profile:'test',stageId:'S02'});
          const c=await openRunnerSession('test',again.id,{lifecycle:false});
          return [p.id===again.id,c.view.savedPlay.stageId,(await runnerLobbyData('student')).unlocked];
        }"""), [True,'S06',['S01']])
        self.assertEqual(self.page.evaluate("async()=>{await buy();return (await readAll('coinSpends')).map(s=>s.amount).sort((a,b)=>a-b);}"), [0,30])
        self.enter('test')
        self.assertEqual(self.page.evaluate('formalRunner.session.view.savedPlay.stageId'), 'S06')
        self.assertEqual(self.page.locator('#formal-stage').input_value(), 'S06')
        self.assertTrue(self.page.locator('#formal-stage').is_disabled())
        self.page.frame_locator('iframe').locator('#runner-toggle').filter(has_text='再開').wait_for()
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"), 2)

    def costs(self, who):
        self.assertEqual(self.page.locator('#runner-home-cost-text').inner_text(), 'テスト中：無料で何回でも' if who=='test' else 'コイン30枚 / 1プレイ')
        self.assertEqual(self.page.locator('#arcade-home-cost-text').inner_text(), 'テスト中：無料で何回でも' if who=='test' else 'コイン100枚 / 1プレイ')

    def test_home_switch_reload_history_and_stale_async(self):
        self.page.evaluate("navigateHome('student')");self.costs('student')
        self.page.once('dialog',lambda d:d.accept())
        self.page.evaluate('beginTestMode()');self.costs('test')
        self.page.evaluate('renderHome()');self.costs('test')
        self.page.reload();self.page.wait_for_function('appReady');self.costs('test')
        self.enter('test')
        self.page.locator('#runner-home').click();self.page.wait_for_function("history.state.screen==='home'")
        self.costs('test')
        self.page.evaluate('returnToStudentHome()');self.costs('student')
        self.page.go_back();self.page.wait_for_function("profile==='test' && history.state.screen==='home'");self.costs('test')
        self.page.go_forward();self.page.wait_for_function("profile==='student' && history.state.screen==='home'");self.costs('student')
        # 古いtest応答が、新しいstudent描画より後で完了するケース。
        self.assertTrue(self.page.evaluate("""async()=>{
          await navigateHome('test');
          const original=runnerLobbyData;let release;
          runnerLobbyData=async who=>{const d=await original(who);if(who==='test')await new Promise(r=>release=r);return d;};
          try {
            const pending=refreshRunnerHome(viewContext());
            while(!release)await new Promise(r=>setTimeout(r,0));
            await navigateHome('student');release();await pending;
            return $('runner-home-cost-text').textContent==='コイン30枚 / 1プレイ';
          }finally{runnerLobbyData=original;}
        }"""))

    def test_representative_layout_and_review_images(self):
        out=Path(os.environ.get('RUNNER_REVIEW_IMAGES','/tmp/runner-137-138'))
        out.mkdir(parents=True,exist_ok=True)
        for width,height in [(390,844),(844,390),(1024,768)]:
            self.page.set_viewport_size(dict(width=width,height=height))
            heights=[]
            for who in ['student','test']:
                self.page.evaluate('who=>navigateHome(who)', who);self.costs(who)
                self.page.evaluate('document.fonts.ready')
                metric=self.page.evaluate("""()=>{
                  const card=document.querySelector('.runner-home-panel'),p=$('runner-home-cost-text'),r=p.getBoundingClientRect();
                  return {height:card.getBoundingClientRect().height,lines:p.getClientRects().length,overflow:document.documentElement.scrollWidth>innerWidth,
                    clipped:[...document.querySelectorAll('.arcade-home-panel *')].some(e=>e.clientWidth>0&&e.scrollWidth>e.clientWidth+1)};
                }""")
                self.assertFalse(metric['overflow']);self.assertFalse(metric['clipped'])
                self.assertLessEqual(metric['lines'],1.1)
                heights.append(metric['height'])
                self.page.locator('.arcade-home-grid').screenshot(path=str(out/f'home-{who}-{width}x{height}.png'), style='main > header { visibility:hidden !important; }')
            self.assertAlmostEqual(*heights,delta=1)
            self.enter('test')
            self.assertEqual(self.page.locator('#formal-stage option:disabled').count(),0)
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width)
            self.page.locator('#runner-choices').screenshot(path=str(out/f'choices-test-{width}x{height}.png'), style='main > header { visibility:hidden !important; }')


del RunnerSessionTest
