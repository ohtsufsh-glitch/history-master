"""Issue #137: 親が所有するリタイア・保存競合・操作/表示の限定試験。合成データのみ。"""
import json
import os
from pathlib import Path
import unittest
import runner_session_test as sessions
import runner_integration_test as integration
from runner_layout_test import MANUAL_FRAME_TIME
from runner_crumbling_test import LAND
from runner_balance_cases import INPUTS
from runner_density_test import INPUTS as DENSITY_INPUTS


class RunnerRetireTest(unittest.TestCase):
    setUpClass = classmethod(sessions.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(sessions.RunnerSessionTest.tearDownClass.__func__)
    setUp = sessions.RunnerSessionTest.setUp
    tearDown = sessions.RunnerSessionTest.tearDown

    def test_running_paused_cancel_confirm_and_positive_lives(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          for(const characterId of ['shiba','salamander'])for(const paused of [false,true]){
            await install(60);const p=await buy({characterId}),c=await openRunnerSession('student',p.id,{lifecycle:false});
            await c.resume();await c.advance(.5);if(paused)await c.pause();
            const before=c.view.state;
            if(!c.beginRetire()||c.beginRetire())throw Error('begin');
            const frozen=JSON.stringify(c.view.state);
            await c.advance(60);await c.jump();await c.resume();
            if(JSON.stringify(c.view.state)!==frozen||(await readAll('runnerPlays'))[0].status!=='active')throw Error('freeze');
            await c.cancelRetire();if(c.view.state.mode!==(paused?'paused':'running'))throw Error('cancel mode');
            if(c.view.state.distance!==before.distance)throw Error('cancel position');
            c.beginRetire();await Promise.all([c.retire(),c.retire(),c.retire()]);
            const d=await snapshotAllStores(),r=d.runnerPlays[0];validateRunnerPlays(d.runnerPlays);
            if(r.status!=='finished'||r.result.reason!=='retire'||r.result.livesRemaining!==before.lives||r.score!==before.score||r.snapshot)throw Error('record');
            if(d.coinSpends.length!==1||d.coinSpends[0].amount!==30||availableCoins(d.coinEvents,d.reviewEvents,d.coinSpends,'student')!==30)throw Error('coins');
          }return true;
        }"""))

    def test_crumbling_support_and_falling_stay_frozen(self):
        self.assertTrue(self.page.evaluate("""async ({landText,plans})=>{
          window.runnerModel=m;const land=eval('('+landText+')');
          for(const falling of [false,true]){
            await install();const p=await buy({profile:'test',stageId:'S05'});
            const s=land('S05',m.getStage('S05',7).crumbling[0].id,plans);
            if(falling){m.startJump(s);while(s.velocityY<=0)m.updateRunner(s,1/120);}
            await saveRunnerState('test',p.id,p.updatedAt,m.snapshotRunner(s));
            const c=await openRunnerSession('test',p.id,{lifecycle:false});await c.resume();c.beginRetire();
            const before=JSON.stringify(c.view.state);for(let i=0;i<200;i++)await c.advance(.1);
            if(before!==JSON.stringify(c.view.state))throw Error('timer advanced');
            await c.retire();const r=c.view.savedPlay;
            if(r.score!==s.score||r.result.livesRemaining!==s.lives||r.score===0)throw Error('score/lives');
            if((await readAll('coinSpends'))[0].amount!==0)throw Error('test price');
          }return true;
        }""",dict(landText=LAND,plans=INPUTS)))

    def test_inflight_save_serializes_and_double_confirm_writes_once(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();await c.advance(.25);
          const save=saveRunnerState;let release,calls=0,terminal=0;
          saveRunnerState=async(...args)=>{calls++;if(args[3].reason==='retire')terminal++;if(calls===1)await new Promise(r=>release=r);return save(...args);};
          try{
            const pending=c.checkpoint();c.beginRetire();const end=c.retire(),again=c.retire();
            if(calls!==1||(await readAll('runnerPlays'))[0].status!=='active')throw Error('not serialized');
            release();await Promise.all([pending,end,again]);
            if(calls!==2||terminal!==1||c.view.dirty||c.view.error||c.view.savedPlay.result.reason!=='retire')throw Error('finish count');
          }finally{saveRunnerState=save;}
          return (await readAll('coinSpends')).length===1;
        }"""))

    def test_failed_finish_sync_and_async_keeps_paid_active_and_recovers(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          for(const asyncFailure of [false,true]){
            await install();const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();await c.advance(.25);await c.pause();c.beginRetire();
            const put=IDBObjectStore.prototype.put;
            IDBObjectStore.prototype.put=function(v){
              if(this.name==='runnerPlays'&&v.status==='finished'){
                if(!asyncFailure)throw Error('disk full');
                put.call(this,v);return this.add(v);
              }return put.call(this,v);
            };
            try{if(!await rejected(()=>c.retire()))throw Error('no failure');}finally{IDBObjectStore.prototype.put=put;}
            const record=(await readAll('runnerPlays'))[0];
            if(record.status!=='active'||!c.view.error||!c.view.dirty||(await buy()).id!==p.id)throw Error('lost active');
            const recovery=await openRunnerSession('student',p.id,{lifecycle:false});await recovery.resume();
            if(recovery.view.state.distance!==record.snapshot.distance)throw Error('recovery');
            recovery.beginRetire();await recovery.retire();if((await readAll('coinSpends')).length!==1)throw Error('charged twice');
          }return true;
        }"""))

    def test_real_second_tab_cas_and_already_finished_priority(self):
        other=self.context.new_page();other.goto(self.url);other.wait_for_function('appReady')
        play_id=self.page.evaluate("async()=>{const p=await buy();window.c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();c.beginRetire();return p.id;}")
        other.evaluate("async id=>{window.c=await openRunnerSession('student',id,{lifecycle:false});await c.resume();await c.advance(.25);await c.pause();}",play_id)
        self.assertTrue(self.page.evaluate("async()=>await rejected(()=>c.retire())&&c.view.error.includes('別の画面')"))
        self.assertEqual(other.evaluate("async()=>[(await readAll('runnerPlays'))[0].status,(await readAll('coinSpends')).length]"),['active',1])
        # A separate tab has already finished; a late retire must adopt that result.
        self.page.evaluate("async()=>{window.c=await openRunnerSession('student',c.view.savedPlay.id,{lifecycle:false});c.beginRetire();}")
        other.evaluate("async()=>{await c.resume();while(c.view.state.mode!=='finished')await c.advance(.05);}")
        self.assertTrue(self.page.evaluate("async()=>{await c.retire();return c.view.savedPlay.result.reason==='gameover'&&c.view.state.reason==='collision'&&!c.view.dirty;}"))

    def test_clear_before_and_after_retire_is_never_overwritten(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});c.beginRetire();
          const s=m.createRunnerState(m.STAGES[0]);s.distance=s.goalDistance;s.nextSpawn=s.course.length;s.objects=s.course.map((e,id)=>({...e,id,spawnDistance:e.at*200,x:1008-(s.distance-e.at*200)})).filter(o=>o.x+40>=0);s.mode='finished';s.reason='clear';
          const clear=await saveRunnerState('student',p.id,p.updatedAt,m.snapshotRunner(s));
          await c.retire();if(c.view.savedPlay.updatedAt!==clear.updatedAt||c.view.state.reason!=='clear'||c.beginRetire())return false;
          return (await readAll('runnerPlays'))[0].result.reason==='clear';
        }"""))

    def test_inflight_active_save_losing_to_clear_adopts_authoritative_finish(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});
          const save=saveRunnerState;let release;
          saveRunnerState=async(...args)=>{await new Promise(r=>release=r);return save(...args);};
          const pending=c.checkpoint();c.beginRetire();const end=c.retire();
          try {
            const s=m.createRunnerState(m.STAGES[0]);s.distance=s.goalDistance;s.nextSpawn=s.course.length;
            s.objects=s.course.map((e,id)=>({...e,id,spawnDistance:e.at*200,x:1008-(s.distance-e.at*200)})).filter(o=>o.x+40>=0);
            s.mode='finished';s.reason='clear';await save('student',p.id,p.updatedAt,m.snapshotRunner(s));
            saveRunnerState=save;release();await Promise.all([pending,end]);
            return c.view.savedPlay.result.reason==='clear'&&c.view.state.reason==='clear'&&!c.view.error&&!c.view.dirty;
          }finally{saveRunnerState=save;}
        }"""))

    def test_retire_immediately_before_goal_does_not_clear(self):
        self.assertTrue(self.page.evaluate("""async plans=>{
          const p=await buy(),s=m.createRunnerState(m.STAGES[0]);s.mode='running';let n=0;
          while(s.mode==='running'&&s.distance<s.goalDistance-2){
            if(n<plans.length&&s.elapsed+1e-8>=plans[n]){m.startJump(s);n++;}
            m.updateRunner(s,1/120);
          }
          if(s.mode!=='running'||s.score!==100)throw Error('near goal fixture');
          await saveRunnerState('student',p.id,p.updatedAt,m.snapshotRunner(s));
          const c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();c.beginRetire();
          await c.advance(1);await c.retire();
          const d=await runnerLobbyData('student');
          return c.view.savedPlay.result.reason==='retire'&&c.view.savedPlay.score===100&&d.unlocked.join()==='S01'&&!d.summary.bestByStage.S01;
        }""",DENSITY_INPUTS['S01']))

    def test_retire_only_ranking_mixed_legacy_results_and_validation(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});c.beginRetire();await c.retire();
          const r=c.view.savedPlay;r.score=100;validateRunnerPlays([r]);
          const summary=summarizeRunnerPlays([r],'student');
          if(Object.keys(summary.bestByStage).length||Object.keys(summary.bestByStageCharacter).length||summary.unlockedStageIds.join()!=='S01')throw Error('ranking');
          const d={records:[r],summary,secret:false};const result=runnerResultData(d,r);
          if(result.stageRecord||result.characterRecord||result.unlocked.length)throw Error('new record');
          for(const lives of [0,-1,3]){const bad=structuredClone(r);bad.result.livesRemaining=lives;try{validateRunnerPlays([bad]);return false;}catch{}}
          const old={...r,id:'legacy',score:10,result:{...r.result,reason:'gameover',livesRemaining:0}};
          const clear={...r,id:'clear',score:0,result:{...r.result,reason:'clear',livesRemaining:1}};
          validateRunnerPlays([r,old,clear]);const mixed=summarizeRunnerPlays([r,old,clear],'student');
          return mixed.bestByStage.S01.id==='legacy'&&mixed.unlockedStageIds.includes('S02')&&!Object.keys(summarizeRunnerPlays([r],'test').bestByStage).length;
        }"""))

    def test_v10_export_restore_reload_and_old_app_rollback_limit(self):
        self.page.evaluate("""async()=>{
          await plushInstall(plushFixture([],'student'));
          const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();c.beginRetire();await c.retire();
          window.before=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:before});
        }""")
        with self.page.expect_download() as download:
            self.page.evaluate('exportBackup()')
        data=json.loads(Path(download.value.path()).read_text())
        self.assertEqual(data['backupVersion'],10)
        self.page.evaluate("async backup=>{await replaceAllStores(validateBackup(backup));}",data)
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate("async()=>{const d=await runnerLobbyData('student');return [d.active||null,d.records[0].result.reason,d.records[0].result.livesRemaining,d.records[0].score,Object.keys(d.summary.bestByStage).length,db.version,BACKUP_VERSION];}"),[None,'retire',2,0,0,10,10])
        # Old v1.7.54 does not accept the new reason; record the exact rollback limit.
        import subprocess
        old=subprocess.check_output(['git','show','origin/main:index.html'],text=True)
        self.page.route(self.url,lambda route:route.fulfill(body=old,content_type='text/html'))
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertTrue(self.page.evaluate("backup=>{try{validateBackup(backup);return false;}catch{return true;}}",data))


class RunnerRetireUITest(unittest.TestCase):
    setUpClass = classmethod(sessions.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(sessions.RunnerSessionTest.tearDownClass.__func__)
    setUp = sessions.RunnerSessionTest.setUp
    tearDown = sessions.RunnerSessionTest.tearDown
    enter = integration.RunnerIntegrationTest.enter
    start = integration.RunnerIntegrationTest.start

    def test_running_paused_cancel_confirm_focus_keyboard_and_next_purchase(self):
        self.context.add_init_script(MANUAL_FRAME_TIME)
        self.page.evaluate('async()=>install(100)')
        frame=self.start()
        for paused in [False,True]:
            if paused:frame.locator('#runner-toggle').click()
            for action in ['Escape','button']:
                frame.locator('#runner-retire').click()
                self.assertEqual(self.page.locator(':focus').get_attribute('id'),'runner-retire-cancel')
                frozen=self.page.evaluate('formalRunner.session.view.state')
                self.page.wait_for_timeout(100)
                self.assertEqual(frozen,self.page.evaluate('formalRunner.session.view.state'))
                self.page.keyboard.press('Tab');self.assertEqual(self.page.locator(':focus').get_attribute('id'),'runner-retire-confirm')
                # 実時間の待機に頼らず、キャンセルと再表示の各awaitを保留する。
                self.page.evaluate("""()=>{
                  window.originalCancel=formalRunner.session.cancelRetire;window.originalLobby=runnerLobbyData;
                  const cancelGate=new Promise(r=>window.releaseCancel=r),refreshGate=new Promise(r=>window.releaseRefresh=r);
                  window.cancelReturned=false;window.refreshWaiting=false;
                  formalRunner.session.cancelRetire=async()=>{await cancelGate;await originalCancel();cancelReturned=true;};
                  runnerLobbyData=async(...args)=>{if(cancelReturned){refreshWaiting=true;await refreshGate;}return originalLobby(...args);};
                }""")
                if action=='Escape':self.page.keyboard.press('Escape')
                else:self.page.locator('#runner-retire-cancel').click()
                self.assertTrue(self.page.locator('#runner-retire-dialog').evaluate('e=>e.open'))
                self.assertEqual(frozen,self.page.evaluate('formalRunner.session.view.state'))
                self.page.evaluate('releaseCancel()');self.page.wait_for_function('refreshWaiting')
                self.assertTrue(self.page.locator('#runner-retire-dialog').evaluate('e=>e.open'))
                self.page.evaluate('releaseRefresh()')
                self.page.wait_for_function("!document.querySelector('#runner-retire-dialog').open")
                self.assertEqual(self.page.evaluate('formalRunner.session.view.state.mode'),'paused' if paused else 'running')
                self.assertTrue(frame.locator('#runner-retire').evaluate("e=>e===document.activeElement"))
                self.page.evaluate('()=>{formalRunner.session.cancelRetire=originalCancel;runnerLobbyData=originalLobby;}')
        frame.locator('#runner-retire').click();self.page.locator('#runner-retire-confirm').click()
        frame.locator('#runner-result-title').filter(has_text='リタイアしました').wait_for()
        self.assertEqual(frame.locator('#runner-result-record').inner_text(),'')
        self.assertEqual(frame.locator('#runner-result-unlock').inner_text(),'')
        self.assertFalse(self.page.locator('#formal-character').is_disabled())
        self.page.locator('#formal-character-cards [data-choice="goldfish"]').click()
        self.assertTrue(frame.locator('#runner-retire').is_hidden())
        self.page.once('dialog',lambda d:d.accept());frame.locator('#runner-toggle').click()
        self.page.wait_for_function('!runnerStarting')
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).map(s=>s.amount),formalRunner.session.view.state.characterId]"),[[30,30],'goldfish'])

    def test_dialog_rotation_lifecycle_duplicate_save_and_failure_recovery(self):
        self.context.add_init_script(MANUAL_FRAME_TIME)
        frame=self.start();frame.locator('#runner-retire').click()
        self.page.evaluate("()=>{window.dispatchEvent(new Event('pagehide'));window.dispatchEvent(new Event('pageshow'));}")
        self.page.set_viewport_size(dict(width=844,height=390))
        self.assertTrue(self.page.locator('#runner-retire-dialog').is_visible())
        self.assertEqual(self.page.evaluate('formalRunner.session.view.state.mode'),'paused')
        self.page.evaluate("""()=>{window.originalSave=saveRunnerState;window.finishedCalls=0;
          saveRunnerState=async(...args)=>{if(args[3].reason==='retire'){finishedCalls++;await new Promise(r=>window.releaseFinish=r);}return originalSave(...args);};}""")
        self.page.locator('#runner-retire-confirm').click()
        self.page.wait_for_function("typeof window.releaseFinish === 'function'")
        self.page.evaluate("document.querySelector('#runner-retire-confirm').click()")
        self.assertTrue(self.page.locator('#formal-character').is_disabled())
        self.assertTrue(self.page.locator('#runner-retire-cancel').is_disabled())
        self.assertEqual(self.page.evaluate('finishedCalls'),1)
        self.page.evaluate('releaseFinish()');frame.locator('#runner-result-title').filter(has_text='リタイアしました').wait_for()
        self.page.evaluate('()=>{saveRunnerState=originalSave;}')
        # New free test-profile play; an actual failed finish must retain selection locks.
        self.page.evaluate("async()=>{await navigate('runner','test');}")
        frame=self.page.frame_locator('iframe');frame.locator('#runner-toggle').click();self.page.wait_for_function('!runnerStarting')
        frame.locator('#runner-retire').click()
        self.page.evaluate("()=>{saveRunnerState=async()=>{throw Error('disk full')};}")
        self.page.locator('#runner-retire-confirm').click()
        frame.locator('#runner-toggle').filter(has_text='最後の保存から再開（無料）').wait_for()
        self.page.wait_for_function("!document.querySelector('#runner-retire-dialog').open")
        self.assertTrue(frame.locator('#runner-toggle').evaluate('e=>e===document.activeElement'))
        self.assertTrue(self.page.locator('#formal-character').is_disabled())
        self.page.evaluate('()=>{saveRunnerState=originalSave;}')
        frame.locator('#runner-toggle').click();self.page.wait_for_function('!runnerStarting')
        self.assertEqual(self.page.evaluate('formalRunner.session.view.savedPlay.status'),'active')
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).map(s=>s.amount).sort()"),[0,30])
        # キャンセル待ち中に非表示へ移ったタブでは、焦点を明示的に移さない。
        frame.locator('#runner-retire').click()
        self.page.evaluate("""()=>{
          const cancel=formalRunner.session.cancelRetire;
          const gate=new Promise(r=>window.releaseHiddenCancel=r);
          formalRunner.session.cancelRetire=async()=>{await gate;await cancel();};
          const w=document.querySelector('iframe').contentWindow,focus=w.HTMLElement.prototype.focus;
          window.hiddenFocusCalls=0;
          w.HTMLElement.prototype.focus=function(...args){hiddenFocusCalls++;return focus.apply(this,args);};
        }""")
        self.page.locator('#runner-retire-cancel').click()
        self.page.evaluate("""()=>{
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));releaseHiddenCancel();
        }""")
        self.page.wait_for_function("!document.querySelector('#runner-retire-dialog').open")
        self.assertEqual(self.page.evaluate('hiddenFocusCalls'),0)
        self.assertEqual(self.page.evaluate('formalRunner.session.view.state.mode'),'paused')
        self.page.evaluate("()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));}")

    def test_four_viewports_dialog_text_enlargement_and_demo_isolation(self):
        self.context.add_init_script(MANUAL_FRAME_TIME)
        self.page.evaluate("async()=>navigate('runner','test')")
        frame=self.page.frame_locator('iframe');frame.locator('#runner-toggle').click();self.page.wait_for_function('!runnerStarting')
        for width,height in [(390,844),(844,390),(1024,768),(507,768)]:
            with self.subTest(size=(width,height)):
                self.page.set_viewport_size(dict(width=width,height=height));self.page.wait_for_timeout(100)
                self.page.evaluate("()=>{const h=document.querySelector('main > header');scrollTo(0,scrollY+document.querySelector('iframe').getBoundingClientRect().top-(getComputedStyle(h).position==='sticky'?h.getBoundingClientRect().height+8:0));}")
                metrics=self.page.evaluate("""()=>{
                  const f=document.querySelector('iframe'),d=f.contentDocument,w=f.contentWindow;
                  const box=id=>{const b=d.getElementById(id).getBoundingClientRect();return {x:b.x,y:b.y,right:b.right,bottom:b.bottom,width:b.width,height:b.height};};
                  return {w:w.innerWidth,h:w.innerHeight,top:f.getBoundingClientRect().top,retire:box('runner-retire'),jump:box('runner-jump'),canvas:box('runner-canvas'),toggle:box('runner-toggle')};
                }""")
                for name in ['retire','jump','canvas','toggle']:
                    b=metrics[name];self.assertGreater(b['width'],0);self.assertGreaterEqual(b['y'],0)
                    self.assertLessEqual(b['right'],metrics['w']+1);self.assertLessEqual(b['bottom'],metrics['h']+1)
                    self.assertLessEqual(b['bottom']+metrics['top'],height+1)
                self.assertGreaterEqual(metrics['retire']['width'],44);self.assertGreaterEqual(metrics['retire']['height'],44)
                self.assertGreaterEqual(metrics['jump']['y']-metrics['retire']['bottom'],44)
                self.page.evaluate('formalRunner.bridge.resume()')
                self.capture(f'{width}x{height}-play')
                frame.locator('#runner-retire').click()
                self.page.evaluate("document.documentElement.style.fontSize='200%'")
                self.assertTrue(self.page.locator('#runner-retire-confirm').is_visible())
                self.assertLessEqual(self.page.locator('#runner-retire-dialog').evaluate('e=>e.getBoundingClientRect().bottom'),height)
                # Scrollable at large text, with both actions reachable by keyboard.
                self.page.locator('#runner-retire-cancel').focus();self.page.keyboard.press('Tab')
                self.assertEqual(self.page.locator(':focus').get_attribute('id'),'runner-retire-confirm')
                self.page.evaluate("document.documentElement.style.fontSize=''")
                self.capture(f'{width}x{height}-dialog')
                self.page.locator('#runner-retire-cancel').click()
        frame.locator('#runner-retire').click();self.page.locator('#runner-retire-confirm').click()
        frame.locator('#runner-result-title').filter(has_text='リタイアしました').wait_for();self.capture('507x768-result')
        for suffix in ['runner/','runner/?stagePreview=1','runner/?embedded=1']:
            demo=self.context.new_page();demo.goto(self.url.rsplit('/',1)[0]+'/'+suffix)
            self.assertTrue(demo.locator('#runner-retire').is_hidden());demo.close()
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),1)

    def capture(self,name):
        if directory:=os.environ.get('RUNNER_RETIRE_CAPTURE_DIR'):
            Path(directory).mkdir(parents=True,exist_ok=True)
            self.page.screenshot(path=str(Path(directory)/(name+'.png')))
