"""Issue #98: 正式画面・入力・保存の統合。合成データのみ。"""
import unittest
from runner_session_test import RunnerSessionTest
from runner_difficulty_cases import SOLUTIONS


class RunnerIntegrationTest(unittest.TestCase):
    setUpClass = classmethod(RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(RunnerSessionTest.tearDownClass.__func__)
    setUp = RunnerSessionTest.setUp
    tearDown = RunnerSessionTest.tearDown
    # 保存API回帰は別実行。共通セットアップのみ再利用。
    def enter(self):
        self.page.locator('#open-runner').click()
        self.page.locator('#formal-stage option').first.wait_for(state='attached')

    def start(self):
        self.enter()
        frame=self.page.frame_locator('#runner-frame-host iframe')
        frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
        self.page.once('dialog',lambda dialog:dialog.accept())
        frame.locator('#runner-toggle').click()
        frame.locator('#runner-toggle').filter(has_text='一時停止').wait_for()
        return frame

    def test_home_formal_purchase_reload_resume_return(self):
        frame=self.start()
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,(await readAll('coinSpends'))[0].amount]"),[1,30])
        self.page.wait_for_timeout(150)
        frame.locator('#runner-jump').click()
        self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
        frame.locator('#runner-toggle').click()
        self.page.locator('#runner-home').click()
        self.page.locator('#open-runner').wait_for()
        self.page.reload();self.page.wait_for_function('appReady')
        self.page.locator('#open-runner').click()
        frame=self.page.frame_locator('iframe')
        frame.locator('#runner-toggle').filter(has_text='再開').wait_for()
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,formalRunner.session.view.state.mode]"),[1,'paused'])

    def test_locks_secret_profiles_restore_and_free(self):
        self.enter()
        self.assertEqual(self.page.locator('#formal-stage option:disabled').count(),5)
        self.assertEqual(self.page.locator('#formal-character option').count(),4)
        self.page.evaluate("""async()=>{
          await runnerTransaction(['arcadePrizes'],tx=>tx.objectStore('arcadePrizes').put({id:'secret',profile:'student',prizeId:'secret_yuniko'}));
          await renderRunnerLobby();
        }""")
        self.assertEqual(self.page.locator('#formal-character option').count(),5)
        self.page.evaluate("async()=>{await navigate('runner','test');}")
        self.assertEqual(self.page.locator('#formal-character option').count(),4)
        self.page.frame_locator('iframe').locator('#runner-toggle').click()
        self.page.wait_for_function('formalRunner.session !== null')
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends'))[0].amount"),0)

    def test_payment_recheck_missing_mismatch_and_legacy(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy();
          for(const change of [s=>s.amount=0,s=>s.profile='test',s=>s.at='2020-01-01T00:00:00.000Z',s=>s.game='crane']){
            const original=(await readAll('coinSpends'))[0],bad=structuredClone(original);change(bad);
            await runnerTransaction(['coinSpends'],tx=>tx.objectStore('coinSpends').put(bad));
            if(!await rejected(()=>openRunnerSession('student',p.id)))return false;
            await runnerTransaction(['coinSpends'],tx=>tx.objectStore('coinSpends').put(original));
          }
          await runnerTransaction(['coinSpends'],tx=>tx.objectStore('coinSpends').clear());
          return await rejected(()=>openRunnerSession('student',p.id));
        }"""))

    def test_jump_does_not_wait_for_slow_save_and_pending_is_bounded(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();
          const original=saveRunnerState;let release,calls=0;
          saveRunnerState=async(...args)=>{calls++;await new Promise(r=>release=r);return original(...args);};
          try {
            const saving=c.checkpoint();
            await c.jump();if(c.view.state.supportId!==null)return false;
            for(let i=0;i<40;i++)c.checkpoint();
            if(calls!==1)return false;
            saveRunnerState=original;release();await saving;
            return !c.view.dirty&&c.view.savedPlay.snapshot.supportId===null;
          } finally {saveRunnerState=original;}
        }"""))

    def test_difficult_stage_input_order_uses_unchanged_physics(self):
        self.assertTrue(self.page.evaluate("""async solutions=>{
          for(const id of ['S03','S04','S06']) {
            await install(100);
            const state=m.createRunnerState(m.getStage(id,1));
            const at=new Date().toISOString(),p={id:crypto.randomUUID(),profile:'student',game:'runner',schemaVersion:1,stageId:id,characterId:'shiba',stageVersion:1,startedAt:at,updatedAt:at,status:'active',score:0,snapshot:m.snapshotRunner(state)};
            await runnerTransaction(['runnerPlays','coinSpends'],tx=>{tx.objectStore('runnerPlays').put(p);tx.objectStore('coinSpends').put({id:p.id,profile:'student',game:'runner',amount:30,at});});
            const c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();let n=0;
            while(c.view.state.mode==='running') {
              const t=c.view.state.elapsed;
              if(n<solutions[id].perfect.length&&t+1e-8>=solutions[id].perfect[n]){await c.jump();n++;}
              await c.advance(1/60);
            }
            if(c.view.savedPlay.result.reason!=='clear')return false;
          }return true;
        }""",SOLUTIONS))

    def test_demo_and_embedded_urls_never_purchase(self):
        for suffix in ['runner/','runner/?stagePreview=1','runner/?embedded=1&playId=anything']:
            demo=self.context.new_page();demo.goto(self.url.rsplit('/',1)[0]+'/'+suffix)
            if 'embedded' not in suffix:
                demo.locator('#runner-toggle').click()
                self.assertIn('無料',demo.locator('#runner-demo-note').inner_text())
            else:self.assertTrue(demo.locator('#runner-toggle').is_disabled())
            demo.close()
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),0)

    def test_secret_restore_recheck_and_insufficient_balance(self):
        self.enter()
        self.page.evaluate("""async()=>{
          const data=plushFixture(['secret_yuniko'],'student');await replaceAllStores(data);await renderRunnerLobby();
        }""")
        self.assertEqual(self.page.locator('#formal-character option').count(),5)
        self.page.locator('#formal-character-cards [data-choice="secret_yuniko"]').click()
        self.page.evaluate("async()=>{await runnerTransaction(['arcadePrizes'],tx=>tx.objectStore('arcadePrizes').clear());}")
        self.page.frame_locator('iframe').locator('#runner-toggle').click()
        self.page.wait_for_function("!runnerStarting")
        self.assertEqual(self.page.evaluate("async()=>(await readAll('runnerPlays')).length"),0)
        self.page.evaluate("async()=>{await install(29);await renderRunnerLobby();}")
        self.page.frame_locator('iframe').locator('#runner-toggle').click()
        self.page.locator('#runner-info').filter(has_text='あと1コイン').wait_for()
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),0)

    def test_formal_touch_result_and_manual_return(self):
        self.context.close()
        self.context=self.browser.new_context(has_touch=True,viewport=dict(width=390,height=844))
        self.page=self.context.new_page();self.page.goto(self.url);self.page.wait_for_function('appReady')
        self.page.evaluate("async()=>{await navigate('runner','test');}")
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for(state='visible')
        frame=self.page.frame_locator('iframe')
        frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for();frame.locator('#runner-toggle').tap()
        frame.locator('#runner-jump').tap()
        self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
        # 通常走行の結果を実コントローラで確定する。
        self.page.evaluate("""async()=>{
          while(formalRunner.session?.view.state.mode==='running')await formalRunner.bridge.advance(.05);
        }""")
        frame.locator('#runner-result-title').filter(has_text='ゲームオーバー').wait_for()
        self.assertEqual(self.page.evaluate("formalRunner.session.view.savedPlay.result.reason"),'gameover')
        self.page.locator('#runner-home').tap();self.page.locator('#open-runner').wait_for()
        self.assertNotIn('購入済み',self.page.locator('#runner-home-info').inner_text())

    def test_screen_reports_save_failure_and_keeps_paid_record(self):
        frame=self.start()
        self.page.evaluate("""async()=>{
          const original=IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put=function(v){if(this.name==='runnerPlays')throw new Error('disk full');return original.call(this,v);};
          try{await formalRunner.session.checkpoint();}catch{}finally{IDBObjectStore.prototype.put=original;}
        }""")
        frame.locator('#runner-status').filter(has_text='保存に失敗').wait_for()
        self.assertTrue(self.page.evaluate('formalRunner.session.view.dirty'))
        self.assertTrue(self.page.locator('#formal-stage').is_disabled())
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('runnerPlays'))[0].status,(await readAll('coinSpends')).length]"),['active',1])

    def test_representative_touch_layout_and_single_engine(self):
        self.context.close()
        self.context=self.browser.new_context(has_touch=True,viewport=dict(width=390,height=844))
        self.page=self.context.new_page();self.page.goto(self.url);self.page.wait_for_function('appReady')
        self.page.evaluate("async()=>{await navigate('runner','test');}")
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for(state='visible')
        frame=self.page.frame_locator('iframe')
        frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
        # 同じ購入済みiframeを回転させ、再生成・再課金なしで配置を切り替える。
        for width,height in [(390,844),(844,390),(820,1180)]:
            with self.subTest(width=width,height=height):
                self.page.set_viewport_size(dict(width=width,height=height))
                self.page.wait_for_function("""()=> {
                  const f=document.querySelector('iframe'),w=f.contentWindow,d=w.document;
                  const b=d.getElementById('runner-toggle').getBoundingClientRect();
                  return Math.abs(w.innerHeight-f.clientHeight)<2&&b.bottom<=w.innerHeight+1&&
                    d.documentElement.scrollHeight<=w.innerHeight+1;
                }""")
                # 回転では自動スクロールしない。ユーザーが操作位置へ戻った状態で配置を検証。
                self.page.locator('iframe').evaluate("f=>f.scrollIntoView({block:'start'})")
                self.assertEqual(self.page.locator('iframe').count(),1)
                metrics=frame.locator('body').evaluate("""()=>({
                  width:innerWidth,height:innerHeight,
                  scrollHeight:document.documentElement.scrollHeight,
                  scrollWidth:document.documentElement.scrollWidth,
                  landscape:matchMedia('(max-height:500px) and (min-width:481px)').matches,
                  columns:getComputedStyle(document.querySelector('.runner-app')).gridTemplateColumns,
                  canvasColumn:getComputedStyle(document.querySelector('.runner-viewport')).gridColumnStart,
                  controlsColumn:getComputedStyle(document.querySelector('.runner-footer')).gridColumnStart
                })""")
                print('formal iframe',width,height,metrics,flush=True)
                self.assertLessEqual(metrics['scrollHeight'],metrics['height']+1)
                self.assertLessEqual(metrics['scrollWidth'],metrics['width']+1)
                canvas=frame.locator('#runner-canvas').bounding_box()
                jump=frame.locator('#runner-jump').bounding_box()
                toggle=frame.locator('#runner-toggle').bounding_box()
                self.assertGreater(canvas['width'],100)
                self.assertGreater(canvas['height'],50)
                if width==844:
                    self.assertLessEqual(metrics['height'],500)
                    self.assertTrue(metrics['landscape'])
                    self.assertEqual(metrics['canvasColumn'],'1')
                    self.assertEqual(metrics['controlsColumn'],'2')
                    for b in [jump,toggle]:
                        self.assertLessEqual(canvas['x']+canvas['width'],b['x'])
                        self.assertGreater(min(canvas['y']+canvas['height'],b['y']+b['height'])-
                                           max(canvas['y'],b['y']),0)
                else:
                    self.assertFalse(metrics['landscape'])
                    self.assertEqual(len(metrics['columns'].split()),1)
                    self.assertLessEqual(canvas['y']+canvas['height'],jump['y'])
                if width==390:
                    self.assertLessEqual(jump['y']+jump['height'],toggle['y'])
                for b in [jump,toggle]:
                    self.assertGreaterEqual(b['x'],0);self.assertGreaterEqual(b['y'],0)
                    self.assertLessEqual(b['x']+b['width'],width+1)
                    self.assertLessEqual(b['y']+b['height'],height+1)
                    self.assertGreaterEqual(b['height'],44)
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width)
                # 実タッチで開始→即時ジャンプ→停止→手動再開を各サイズで確認。
                frame.locator('#runner-toggle').tap()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
                self.page.wait_for_function("formalRunner.session.view.state.supportId!==null")
                frame.locator('#runner-jump').tap()
                self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
                frame.locator('#runner-toggle').tap()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='paused'")
                distance=self.page.evaluate('formalRunner.session.view.state.distance')
                self.page.wait_for_timeout(100)
                self.assertEqual(self.page.evaluate('formalRunner.session.view.state.distance'),distance)
                frame.locator('#runner-toggle').tap()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
                frame.locator('#runner-toggle').tap()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='paused'")
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),1)

    def test_free_wait_cancel_double_click_and_new_paid_play(self):
        self.page.evaluate('async()=>await install(60)')
        self.enter()
        frame=self.page.frame_locator('iframe')
        frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.evaluate("async()=>[formalRunner.bridge.view.state.mode,(await readAll('runnerPlays')).length,(await readAll('coinSpends')).length]"),['ready',0,0])
        self.page.locator('#formal-character-cards [data-choice="salamander"]').click()
        self.assertEqual(frame.locator('#runner-hearts').inner_text(),'♥♥♥')
        self.page.once('dialog',lambda dialog:dialog.dismiss())
        frame.locator('#runner-toggle').click()
        self.assertEqual(self.page.evaluate("async()=>(await readAll('runnerPlays')).length"),0)
        self.page.once('dialog',lambda dialog:dialog.accept())
        frame.locator('#runner-toggle').evaluate('(b)=>{b.click();b.click();}')
        self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
        self.assertTrue(self.page.locator('#formal-character').is_disabled())
        frame.locator('#runner-toggle').click()
        self.assertTrue(self.page.locator('#formal-stage').is_disabled())
        frame.locator('#runner-toggle').click()
        self.page.evaluate("async()=>{while(formalRunner.session?.view.state.mode==='running')await formalRunner.bridge.advance(.05);}")
        frame.locator('#runner-toggle').filter(has_text='再挑戦').wait_for()
        self.assertTrue(self.page.locator('#formal-character').is_enabled())
        self.page.once('dialog',lambda dialog:dialog.accept())
        frame.locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).map(s=>s.amount),(await readAll('runnerPlays')).length]"),[[30,30],2])

    def test_home_spacing_and_choices_below_game(self):
        self.page.set_viewport_size(dict(width=390,height=844))
        metrics=self.page.evaluate("""()=>{
          const crane=document.querySelector('#game-center-home'),runner=document.querySelector('.runner-home-panel'),weak=crane.previousElementSibling;
          return {gap:runner.getBoundingClientRect().top-crane.getBoundingClientRect().bottom,
            other:crane.getBoundingClientRect().top-weak.getBoundingClientRect().bottom,
            styles:[crane,runner].map(e=>{const s=getComputedStyle(e);return [s.borderRadius,s.padding,s.boxShadow]})};
        }""")
        self.assertEqual(metrics['gap'],metrics['other'])
        self.assertGreaterEqual(metrics['gap'],16)
        self.assertEqual(metrics['styles'][0],metrics['styles'][1])
        self.enter()
        self.page.frame_locator('iframe').locator('#runner-toggle').wait_for(state='visible')
        self.assertTrue(self.page.evaluate("document.querySelector('#runner-choices').getBoundingClientRect().top>=document.querySelector('iframe').getBoundingClientRect().bottom"))
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),0)

    def test_clear_refreshes_unlock_then_selects_without_purchase(self):
        frame=self.start()
        self.page.evaluate("""async times=>{
          const c=formalRunner.session;let n=0;
          while(c.view.state.mode==='running'){
            if(n<times.length&&c.view.state.elapsed+1e-8>=times[n]){await c.jump();n++;}
            await formalRunner.bridge.advance(1/60);
          }
        }""",SOLUTIONS['S01']['perfect'])
        self.assertTrue(self.page.locator('#formal-stage option[value="S02"]').is_enabled())
        self.assertNotIn('🔒',self.page.locator('#formal-stage option[value="S02"]').inner_text())
        self.page.locator('#formal-stage-cards [data-choice="S02"]').click()
        self.page.locator('#formal-character-cards [data-choice="goldfish"]').click()
        self.assertEqual(self.page.evaluate("[formalRunner.bridge.view.state.stageId,formalRunner.bridge.view.state.characterId,formalRunner.bridge.view.state.mode]"),['S02','goldfish','ready'])
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),1)

    def test_unresumable_secret_shows_error_without_exposing_or_rebuying(self):
        self.page.evaluate("""async()=>{
          await runnerTransaction(['arcadePrizes'],tx=>tx.objectStore('arcadePrizes').put({id:'secret',profile:'student',prizeId:'secret_yuniko'}));
          await buy({characterId:'secret_yuniko'});
          await runnerTransaction(['arcadePrizes'],tx=>tx.objectStore('arcadePrizes').clear());
        }""")
        self.enter()
        frame=self.page.frame_locator('iframe')
        frame.locator('#runner-status').filter(has_text='獲得記録を確認できません').wait_for()
        self.assertNotIn('ゆにこ',self.page.locator('#runner').inner_text())
        frame.locator('#runner-toggle').click()
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,(await readAll('runnerPlays'))[0].status,formalRunner.bridge.view.state.mode]"),[1,'active','ready'])


    def test_home_top_and_bottom_entry_show_page_top(self):
        from runner_layout_test import SIZES
        for width,height in SIZES + [(700,900)]:
            self.page.set_viewport_size(dict(width=width,height=height))
            for position in ['top','bottom']:
                with self.subTest(size=(width,height),position=position):
                    self.page.evaluate("navigateHome('test')")
                    self.page.evaluate("p=>scrollTo(0,p==='top'?0:document.documentElement.scrollHeight)",position)
                    if position=='bottom':self.assertGreater(self.page.evaluate('scrollY'),0)
                    # DOM click avoids Playwright's automatic scrolling of an offscreen home card.
                    self.page.evaluate("document.querySelector('#open-runner').click()")
                    self.assertEqual(self.page.evaluate('scrollY'),0)
                    self.page.frame_locator('iframe').locator('#runner-toggle').wait_for()
                    self.assertEqual(self.page.evaluate('scrollY'),0)
                    title=self.page.locator('#runner-heading').bounding_box()
                    header=self.page.locator('main > header').bounding_box()
                    self.assertGreaterEqual(title['y'],header['y']+header['height'])
                    self.assertLessEqual(title['y']+title['height'],height)
                    self.assertEqual(self.page.frames[-1].evaluate('document.scrollingElement.scrollTop'),0)

    def test_home_entry_shows_top_then_preserves_user_scroll(self):
        self.context.close()
        self.context=self.browser.new_context(has_touch=True,viewport=dict(width=390,height=844))
        self.page=self.context.new_page();self.page.goto(self.url);self.page.wait_for_function('appReady')
        for width,height in [(390,844),(844,390),(820,1180)]:
            with self.subTest(width=width,height=height):
                self.page.set_viewport_size(dict(width=width,height=height))
                self.page.evaluate("navigateHome('test')")
                self.page.locator('#open-runner').scroll_into_view_if_needed()
                self.assertGreater(self.page.evaluate('scrollY'),300)
                self.page.locator('#open-runner').tap()
                frame=self.page.frame_locator('#runner-frame-host iframe')
                frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
                # ゲームへの自動移動はせず、タイトルを含むページ先頭を表示。
                self.assertEqual(self.page.evaluate('scrollY'), 0)
                title=self.page.locator('#runner-heading').bounding_box()
                self.assertGreaterEqual(title['y'],0)
                self.assertLess(title['y']+title['height'],height)
                self.page.locator('#formal-character-cards').scroll_into_view_if_needed()
                before=self.page.evaluate('scrollY')
                self.assertGreater(before,300)
                self.page.evaluate("""async()=>{
                  window.entryFrame=formalRunner.frame;
                  window.dispatchEvent(new Event('resize'));
                  window.dispatchEvent(new Event('focus'));
                  window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
                  Object.defineProperty(document,'hidden',{configurable:true,value:true});
                  document.dispatchEvent(new Event('visibilitychange'));
                  Object.defineProperty(document,'hidden',{configurable:true,value:false});
                  document.dispatchEvent(new Event('visibilitychange'));
                  await formalRunner.refresh();
                }""")
                self.page.wait_for_timeout(100)
                self.assertAlmostEqual(self.page.evaluate('scrollY'),before,delta=1)
                self.assertTrue(self.page.evaluate('entryFrame===formalRunner.frame'))

# Imported TestCase must not be rediscovered here.
del RunnerSessionTest
