"""Issue #94: 合成履歴・独立DBで結果の確定順と最高得点UIを検証。"""
import unittest
from runner_integration_test import RunnerIntegrationTest


class RunnerResultsTest(unittest.TestCase):
    setUpClass = classmethod(RunnerIntegrationTest.setUpClass.__func__)
    tearDownClass = classmethod(RunnerIntegrationTest.tearDownClass.__func__)
    setUp = RunnerIntegrationTest.setUp
    tearDown = RunnerIntegrationTest.tearDown
    enter = RunnerIntegrationTest.enter
    start = RunnerIntegrationTest.start

    def finish(self):
        self.page.evaluate("""async()=>{
          const c=formalRunner.session;
          while(c.view.state.mode==='running')await formalRunner.bridge.advance(.05);
          document.querySelector('iframe').contentWindow.refreshFormalRunner();
        }""")

    def test_stage_character_records_and_strict_improvements(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const make=(id,score,characterId='shiba',profile='student',stageId='S01',reason='gameover')=>({
            id,score,characterId,profile,stageId,status:'finished',result:{reason,at:'2020-01-01T00:00:00.000Z'}});
          const rows=[];
          for(const [i,score] of [80,90,100,100,80].entries()){
            const p=make('p'+i,score);rows.push(p);
            const d={records:rows,summary:summarizeRunnerPlays(rows,'student'),secret:false};
            const r=runnerResultData(d,p);
            if(r.stageBest!==Math.max(...rows.map(p=>p.score))||r.stageRecord!==['初記録','新記録！','新記録！','',''][i])return false;
          }
          rows.push(make('gold',90,'goldfish'),make('test',100,'shiba','test','S02'),make('clear',0,'sloth','student','S01','clear'));
          const d=summarizeRunnerPlays(rows,'student');
          return d.bestByStageCharacter['S01:goldfish'].score===90&&d.bestByStage.S01.score===100&&!d.bestByStage.S02&&d.unlockedStageIds.join() ==='S01,S02';
        }"""))
        self.enter()
        self.assertIn('記録なし',self.page.locator('#runner-stage-best').inner_text())
        self.assertEqual(self.page.locator('#runner-character-bests dt').count(),4)
        self.assertEqual(self.page.locator('#runner-stage-bests dt').count(),6)

    def test_committed_result_retry_single_charge_and_home(self):
        self.page.evaluate('install(60)')
        frame=self.start();self.finish()
        frame.locator('#runner-result-title').filter(has_text='ゲームオーバー').wait_for()
        self.assertIn('S01',frame.locator('#runner-result-course').inner_text())
        self.assertIn('しば犬',frame.locator('#runner-result-course').inner_text())
        self.assertIn('初記録',frame.locator('#runner-result-record').inner_text())
        self.assertNotEqual(self.page.locator('#runner-stage-best').inner_text(),'S01 総合：記録なし')
        self.page.once('dialog',lambda d:d.accept())
        frame.locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session.view.state.mode==='running'")
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,(await readAll('coinSpends')).reduce((s,p)=>s+p.amount,0)]"),[2,60])
        self.finish()
        self.assertNotIn('新記録',frame.locator('#runner-result-record').inner_text())
        frame.locator('#runner-toggle').click()
        self.page.locator('#runner-info').filter(has_text='あと30コイン').wait_for()
        self.page.locator('#runner-home').click()
        self.page.locator('#open-runner').wait_for()

    def test_pending_commit_never_confirms_then_recovers_without_charge(self):
        self.page.set_viewport_size(dict(width=390,height=844))
        frame=self.start()
        self.page.evaluate("""()=>{
          window.originalSave=saveRunnerState;
          saveRunnerState=async(...args)=>{
            if(args[3].mode==='finished')await new Promise(r=>window.releaseFinish=r);
            return originalSave(...args);
          };
          window.finishing=(async()=>{
            while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05);
          })();
        }""")
        self.page.wait_for_function('typeof releaseFinish === "function"')
        self.page.evaluate("document.querySelector('iframe').contentWindow.refreshFormalRunner()")
        self.assertIn('保存中',frame.locator('#runner-result-title').inner_text())
        self.assert_result_layout(frame,confirmed=False)
        self.assertEqual(frame.locator('#runner-result-record').inner_text(),'')
        self.assertEqual(frame.locator('#runner-result-unlock').inner_text(),'')
        self.assertTrue(frame.locator('#runner-toggle').is_disabled())
        self.page.evaluate('async()=>{saveRunnerState=originalSave;releaseFinish();await finishing;}')
        frame.locator('#runner-result-record').filter(has_text='初記録').wait_for()
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),1)

    def test_failed_finish_is_unconfirmed_and_free_recovery(self):
        self.page.set_viewport_size(dict(width=390,height=844))
        frame=self.start()
        self.page.evaluate("""async()=>{
          const original=IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put=function(v){if(this.name==='runnerPlays'&&v.status==='finished')throw new Error('test full');return original.call(this,v);};
          try{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(.05);}catch{}
          finally{IDBObjectStore.prototype.put=original;}
          document.querySelector('iframe').contentWindow.refreshFormalRunner();
        }""")
        self.assertIn('まだ保存',frame.locator('#runner-result-title').inner_text())
        self.assert_result_layout(frame,confirmed=False)
        self.assertEqual(frame.locator('#runner-result-record').inner_text(),'')
        frame.locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,formalRunner.session.view.state.mode]"),[1,'running'])

    def layout(self, frame):
        return frame.locator('body').evaluate("""()=>({
          width:innerWidth,height:innerHeight,scroll:document.documentElement.scrollHeight,
          boxes:['.runner-viewport','.runner-stage','.runner-controls'].map(s=>{
            const b=document.querySelector(s).getBoundingClientRect();return [b.x,b.y,b.width,b.height];
          })})""")

    def assert_result_layout(self, frame, confirmed=True):
        self.assertEqual(frame.locator('#runner-result-home').count(),0)
        metrics=self.layout(frame)
        self.assertLessEqual(metrics['scroll'],metrics['height']+1)
        self.assertLessEqual(frame.locator('body').evaluate('()=>document.documentElement.scrollWidth'),metrics['width'])
        panel=frame.locator('#runner-result').evaluate('(e)=>[e.clientHeight,e.scrollHeight]')
        if metrics['width']<480 and metrics['height']>500:
            self.assertLessEqual(panel[1],panel[0]+1)
        selectors=['#runner-result-title','#runner-result-message','#runner-result-score',
                   '#runner-result-progress','#runner-toggle']
        if confirmed:
            selectors+=['#runner-result-course','#runner-result-best','#runner-result-character-best']
        for selector in selectors:
            self.assertTrue(frame.locator(selector).is_visible())

    def test_sizes_result_scroll_and_buttons(self):
        for width,height in [(390,844),(844,390),(820,1180)]:
            with self.subTest(width=width,height=height):
                self.page.set_viewport_size(dict(width=width,height=height))
                self.page.evaluate('async()=>{await navigateHome();await install(60);}')
                self.enter()
                frame=self.page.frame_locator('iframe')
                frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
                before=self.layout(frame)
                iframe_before=self.page.locator('iframe').evaluate('e=>[e.clientWidth,e.clientHeight]')
                self.page.once('dialog',lambda d:d.accept())
                frame.locator('#runner-toggle').click()
                frame.locator('#runner-toggle').click()
                self.assertEqual(self.layout(frame)['boxes'],before['boxes'])
                frame.locator('#runner-toggle').click()
                scroll_before=self.page.evaluate('scrollY')
                self.finish()
                frame.locator('#runner-result-title').filter(has_text='ゲームオーバー').wait_for()
                self.assert_result_layout(frame)
                self.assertEqual(self.layout(frame)['boxes'],before['boxes'])
                self.assertEqual(self.page.locator('iframe').evaluate('e=>[e.clientWidth,e.clientHeight]'),iframe_before)
                self.assertAlmostEqual(self.page.evaluate('scrollY'),scroll_before,delta=1)
                self.assertTrue(frame.locator('#runner-toggle').is_enabled())

    def test_clear_overlay_records_unlock_and_retry(self):
        from runner_difficulty_cases import SOLUTIONS
        self.page.set_viewport_size(dict(width=390,height=844))
        frame=self.start()
        self.page.evaluate("""async times=>{
          const c=formalRunner.session;let n=0;
          while(c.view.state.mode==='running'){
            if(n<times.length&&c.view.state.elapsed+1e-8>=times[n]){await c.jump();n++;}
            await formalRunner.bridge.advance(1/60);
          }
          document.querySelector('iframe').contentWindow.refreshFormalRunner();
        }""",SOLUTIONS['S01']['perfect'])
        frame.locator('#runner-result-title').filter(has_text='クリア！').wait_for()
        self.assert_result_layout(frame)
        self.assertIn('S02',frame.locator('#runner-result-unlock').inner_text())
        self.assertIn('初記録',frame.locator('#runner-result-record').inner_text())
        self.assertTrue(frame.locator('#runner-toggle').is_enabled())

    def test_long_result_and_enlarged_text_remain_readable(self):
        self.page.set_viewport_size(dict(width=390,height=844))
        frame=self.start();self.finish()
        panel=frame.locator('#runner-result')
        # 表示だけのストレスケース。実際の得点/保存レコードは書き換えない。
        for selector,text in [('#runner-result-course','S06 ゴールへの大冒険 ／ オオサンショウウオ'),
                              ('#runner-result-record','ステージ 新記録！ ／ キャラクター 新記録！'),
                              ('#runner-result-unlock','S06 が遊べるようになったよ！')]:
            panel.locator(selector).evaluate('(e,text)=>e.textContent=text',text)
        self.assert_result_layout(frame)
        self.page.frames[-1].evaluate("document.documentElement.style.fontSize='200%'")
        panel.locator('#runner-result-progress').scroll_into_view_if_needed()
        self.assertTrue(panel.locator('#runner-result-progress').evaluate("""e=>{
          const b=e.getBoundingClientRect(),p=e.closest('.runner-result').getBoundingClientRect();
          return b.top>=p.top&&b.bottom<=p.bottom;
        }"""))
        frame.locator('#runner-toggle').scroll_into_view_if_needed()
        self.assertTrue(frame.locator('#runner-toggle').is_enabled())

    def test_top_home_buttons_touch_preserves_profile(self):
        self.context.close()
        self.context=self.browser.new_context(has_touch=True,viewport=dict(width=390,height=844))
        self.page=self.context.new_page();self.page.goto(self.url);self.page.wait_for_function('appReady')
        for screen,selector in [('runner','#runner-home'),('arcade','#arcade-back')]:
            self.page.evaluate('(screen)=>navigate(screen,"test")',screen)
            self.page.locator(selector).tap()
            self.page.locator('#open-runner').wait_for()
            self.assertEqual(self.page.evaluate('profile'),'test')

    def test_top_home_buttons_share_style_and_keyboard_navigation(self):
        styles=[]
        for screen,selector in [('runner','#runner-home'),('arcade','#arcade-back')]:
            self.page.evaluate('(screen)=>navigate(screen,"test")',screen)
            button=self.page.get_by_role('button',name='学習ホームへ戻る',exact=True)
            self.assertEqual(button.count(),1)
            self.assertEqual(button.get_attribute('id'),selector[1:])
            styles.append(button.evaluate("""e=>{
              const s=getComputedStyle(e);return ['backgroundColor','border','borderRadius','color','fontSize','minHeight'].map(k=>s[k]);
            }"""))
            self.assertGreaterEqual(button.bounding_box()['height'],48)
            self.assertTrue(button.evaluate('e=>e.parentElement.firstElementChild===e'))
            button.focus()
            self.assertTrue(button.evaluate('e=>e.matches(":focus-visible")'))
            button.press('Enter')
            self.page.locator('#open-runner').wait_for()
            self.assertEqual(self.page.evaluate('profile'),'test')
        self.assertEqual(styles[0],styles[1])

    def test_refresh_records_secret_reset_and_other_profile(self):
        self.enter()
        self.page.evaluate("""async()=>{
          const at='2020-01-01T00:00:00.000Z';
          const p={id:'synthetic',profile:'student',game:'runner',schemaVersion:1,stageId:'S01',characterId:'secret_yuniko',stageVersion:1,startedAt:at,updatedAt:at,status:'finished',score:100,result:{reason:'gameover',at,livesRemaining:0}};
          await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').put(p));
          await formalRunner.refresh();
        }""")
        self.assertIn('100点',self.page.locator('#runner-stage-best').inner_text())
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        self.page.evaluate("async()=>{await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').clear());await formalRunner.refresh();}")
        self.assertIn('記録なし',self.page.locator('#runner-stage-best').inner_text())
        self.page.evaluate("async()=>{await navigate('runner','test');}")
        self.assertIn('記録なし',self.page.locator('#runner-stage-best').inner_text())

    def test_backup_restore_and_resets_refresh_visible_records(self):
        self.enter()
        self.page.evaluate("""async()=>{
          const d=plushFixture(['secret_yuniko'],'student');
          const at='2020-01-01T00:00:00.000Z';
          d.runnerPlays=[{id:'runner-backup',profile:'student',game:'runner',schemaVersion:1,
            stageId:'S01',characterId:'secret_yuniko',stageVersion:1,startedAt:at,updatedAt:at,
            status:'finished',score:90,result:{reason:'clear',at,livesRemaining:1}}];
          d.coinSpends.push({id:'runner-backup',profile:'student',game:'runner',amount:30,at});
          validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:d});
          await replaceAllStores(d);await formalRunner.refresh();
        }""")
        self.assertIn('90点',self.page.locator('#runner-stage-best').inner_text())
        self.assertIn('ゆにこ',self.page.locator('#runner-character-bests').inner_text())
        self.page.evaluate("async()=>{await performReset({student:true});await formalRunner.refresh();}")
        self.assertIn('記録なし',self.page.locator('#runner-stage-best').inner_text())
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        self.page.evaluate("async()=>{await performReset({},true);await renderRunnerLobby();}")
        self.assertIn('記録なし',self.page.locator('#runner-stage-best').inner_text())


del RunnerIntegrationTest
