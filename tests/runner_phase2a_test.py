"""Issue #85 phase 2A: S04 only. Public synthetic data and temporary localhost browsers."""
import json
from pathlib import Path
import unittest

import runner_phase1_test as phase1
import runner_canvas_test as canvas

BASE = json.loads((Path(__file__).parent / 'fixtures/runner85-phase2a-base.json').read_text())
INPUTS = [7.55, 12, 13.95, 15.85, 17.75, 24.55]


class RunnerPhase2APhysicsTest(unittest.TestCase):
    setUpClass = classmethod(phase1.RunnerPhase1PhysicsTest.setUpClass.__func__)
    tearDownClass = classmethod(phase1.RunnerPhase1PhysicsTest.tearDownClass.__func__)
    model = phase1.RunnerPhase1PhysicsTest.model
    model_runner = canvas.RunnerCanvasTest.model_runner
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    open_runner = canvas.RunnerCanvasTest.open_runner
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    assert_isolated = canvas.RunnerCanvasTest.assert_isolated
    toggle = canvas.RunnerCanvasTest.toggle
    tap = canvas.RunnerCanvasTest.tap

    def test_definitions_keep_all_previous_versions_and_only_replace_latest_s04(self):
        p = self.model()
        self.assertEqual(p.evaluate("runnerModel.STAGES.filter(s=>s.stageId!=='S04')"),
                         [s for s in BASE['stages'] if s['stageId'] != 'S04'])
        self.assertEqual(p.evaluate("runnerModel.getStage('S04',1)"), BASE['stages'][3])
        self.assertEqual(p.evaluate("runnerModel.STAGES.map(s=>[s.stageId,s.stageVersion??1,s.goalDistance,s.course.filter(e=>e.type==='star').length])"),
                         [['S01',1,4000,10],['S02',2,5000,10],['S03',2,6000,10],
                          ['S04',2,7000,10],['S05',1,7200,10],['S06',1,8000,10]])

    def test_shiba_clear_requires_landing_and_top_jumps_at_three_rates(self):
        p = self.model()
        rows = p.evaluate("""inputs=>[30,60,120].map(hz=>{
          const stage=runnerModel.getStage('S04',2);
          return {hz,good:phase1Trial(stage,inputs,hz),idle:phase1Trial(stage,[],hz),
            noTop:phase1Trial(stage,inputs.filter((_,i)=>i<2||i>4),hz),
            noBlock:phase1Trial({...stage,course:stage.course.filter(e=>e.type!=='platform')},inputs,hz),
            oneTop:phase1Trial(stage,inputs.filter((_,i)=>i!==3&&i!==4),hz)};
        })""", INPUTS)
        for r in rows:
            self.assertEqual((r['good']['reason'],r['good']['score'],r['good']['hits'],r['good']['lives']), ('clear',100,0,2),r)
            self.assertTrue(r['good']['accepted'])
            self.assertEqual(len(r['good']['landings']),1)
            for jump in r['good']['jumps'][2:5]:
                self.assertNotIn(jump['support'],(None,'ground'))
            for key in ('idle','noTop','noBlock','oneTop'):
                self.assertEqual((r[key]['reason'],r[key]['lives']),('collision',0),(key,r))
        print('S04: shiba 100 points/no hits at 30/60/120Hz; idle/no block/no top jumps/only one top jump fail')

    def test_top_jumps_cannot_be_replaced_by_three_hearts_or_ground_running(self):
        p = self.model()
        out = p.evaluate("""()=>{
          const m=runnerModel,stage=m.getStage('S04',2),rows=[];
          // 3ハートの通常キャラで岩を避け、足場へ登った後は走るだけ。
          const s=m.createRunnerState(stage,'salamander');s.mode='running';
          const inputs=[1600/230-.41,2400/230];let n=0;const hits=[];let landed=false;
          while(s.mode==='running'){
            if(n<inputs.length&&s.elapsed+1e-9>=inputs[n]){m.startJump(s);n++;}
            const lives=s.lives;m.updateRunner(s,1/120);
            if(s.supportId!==null&&s.supportId!=='ground')landed=true;
            if(lives>s.lives)hits.push(s.distance);
          }
          return {reason:s.reason,lives:s.lives,landed,hits};
        }""")
        self.assertTrue(out['landed'],out)
        self.assertEqual((out['reason'],out['lives']),('collision',0),out)
        self.assertEqual(len(out['hits']),3)
        for a,b in zip(out['hits'],out['hits'][1:]):
            self.assertGreater(b-a,230)  # 無敵1秒で次の鳥まで通過できない。

    def test_input_windows_and_reaction_time(self):
        p = self.model()
        rows = p.evaluate("""inputs=>inputs.map((_,action)=>{
          let streak=0,longest=0,start=null,range=null;
          for(let frame=-30;frame<=30;frame++){
            const r=phase1Trial(runnerModel.getStage('S04',2),inputs.map((t,i)=>t+(i===action?frame/60:0)));
            if(r.reason==='clear'&&r.hits===0&&r.score===100&&r.accepted){
              if(!streak)start=frame/60;streak++;if(streak>longest){longest=streak;range=[start,frame/60];}
            }else streak=0;
          }return {action,range,width:(longest-1)/60};
        })""", INPUTS)
        for r in rows:
            self.assertGreaterEqual(r['width']+1e-9,.15,r)
        print('S04_INPUT_WINDOWS='+json.dumps(rows))
        # 鳥の全体が画面内に入ってからジャンプ入力まで3秒以上ある。
        self.assertTrue(p.evaluate("""inputs=>{
          const m=runnerModel,s=m.createRunnerState(m.getStage('S04',2));
          return s.birds.every((b,i)=>inputs[i+2]-(b.x-(960-m.CHARACTER_X-m.BIRD_RADIUS))/s.speed>3);
        }""",INPUTS))

    def test_collision_circle_and_every_frame_restore_pause_with_birds(self):
        p = self.model()
        self.assertTrue(p.evaluate("""inputs=>{
          const m=runnerModel,stage=m.getStage('S04',2);
          // 境界は描画と同じ半径28。静止高度は足場上のキャラ中心と一致。
          const probe=m.createRunnerState(stage),bird=probe.birds[0];probe.feetY=370;
          for(const [dx,hit] of [[55.99,true],[56.01,false]]){
            probe.distance=bird.x-dx;if(m.touchesBird(probe,bird)!==hit)throw Error('circle edge');
          }
          probe.distance=bird.x;probe.feetY=250;if(m.touchesBird(probe,bird))throw Error('jump not safe');
          probe.feetY=470;if(m.touchesBird(probe,bird))throw Error('ground overlap');
          const seen=new Set();
          for(const path of ['clear','hit']){
            const s=m.createRunnerState(stage);s.mode='running';let n=0;
            const plan=path==='clear'?inputs:inputs.filter((_,i)=>i<2);
            for(let f=0;f<2200&&s.mode==='running';f++){
              if(n<plan.length&&f/60+1e-9>=plan[n]){m.startJump(s);n++;}
              m.updateRunner(s,1/60);
              if(s.supportId!==null&&s.supportId!=='ground')seen.add('platform');
              if(s.invincibleRemaining)seen.add('shield');if(s.airAction==='jump'&&s.jumpOriginY===370)seen.add('topJump');
              const r=m.restoreRunner({stageId:'S04',stageVersion:2,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});
              if(JSON.stringify(s.birds.map(b=>m.birdCenter(s,b)))!==JSON.stringify(r.birds.map(b=>m.birdCenter(r,b))))throw Error('bird moved on restore');
              if(r.mode!=='finished'){
                const before=JSON.stringify(r);m.updateRunner(r,99);if(JSON.stringify(r)!==before||m.startJump(r))throw Error('pause moved');
                m.resumeRunner(r);
              }
              const c=structuredClone(s);m.updateRunner(c,1/60);m.updateRunner(r,1/60);
              if(JSON.stringify(m.snapshotRunner(c))!==JSON.stringify(m.snapshotRunner(r)))throw Error('resume divergence');
            }
          }return ['platform','shield','topJump'].every(x=>seen.has(x));
        }""",INPUTS))

    def test_real_touch_route_and_identical_bird_rendering_on_phone_tablet(self):
        model = self.model()
        stage = model.evaluate("runnerModel.getStage('S04',2)")
        for width,height in [(390,844),(1024,768)]:
            p,errors,requests = self.manual_runner(course=stage,width=width,height=height)
            # 計測のみ。実Canvasの鳥の輪郭円を取り出す。
            p.evaluate("""()=>{window.birdPaint=[];const proto=CanvasRenderingContext2D.prototype,arc=proto.arc;
              const transform=proto.setTransform;proto.setTransform=function(...args){birdPaint.length=0;return transform.apply(this,args);};
              proto.arc=function(x,y,r,...rest){if(this.fillStyle==='#e64b65')birdPaint.push({x,y,r});return arc.call(this,x,y,r,...rest);};}""")
            self.toggle(p);p.evaluate('runnerClock.step(0)');now=0
            for i,t in enumerate(INPUTS):
                p.evaluate('ms=>runnerClock.advance(ms,60)',t*1000-now)
                self.tap(p);now=t*1000
                if i==2:
                    p.evaluate('birdPaint.length=0;runnerClock.advance(200,60)');now+=200
                    circles=p.evaluate('birdPaint')
                    self.assertEqual([c['y'] for c in circles],[327]*2)
                    self.assertEqual([c['r'] for c in circles],[26]*2)
                    for c,x in zip(circles,[236,616]):
                        self.assertAlmostEqual(c['x'],x,delta=.01) # stroke幅4を含め半径28。
            p.evaluate('ms=>runnerClock.advance(ms,60)',35000-now)
            self.assertEqual(p.locator('#runner-result-title').inner_text(),'クリア！')
            self.assertEqual(p.locator('#runner-score').inner_text(),'100')
            self.assert_isolated(p,errors,requests)


class RunnerPhase2ACompatibilityTest(unittest.TestCase):
    setUpClass = classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass = classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp = phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown = phase1.RunnerPhase1CompatibilityTest.tearDown

    def test_old_s04_paid_snapshots_keep_original_course_and_save_reload(self):
        rows=self.page.evaluate("""async base=>{
          const rows=[];
          for(const {phase,play} of base.states){
            await installPhase([play]);const before=await snapshotAllStores();
            let c=await openRunnerSession('student',play.id,{lifecycle:false});
            if(!runnerCanResume(play)||(await buyLegacy({stageId:'S04'})).id!==play.id)throw Error('legacy purchase changed');
            const s=m.restoreRunner(play);await c.resume();m.resumeRunner(s);await c.advance(.1);m.updateRunner(s,.1);await c.pause();s.mode='paused';
            c=await openRunnerSession('student',play.id,{lifecycle:false});
            if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(m.snapshotRunner(s)))throw Error('legacy trajectory');
            const after=await snapshotAllStores();
            for(const name of BACKUP_STORES.filter(x=>x!=='runnerPlays'))if(JSON.stringify(before[name])!==JSON.stringify(after[name]))throw Error('unrelated store '+name);
            rows.push([phase,c.view.state.stageVersion,c.view.state.goalDistance,c.view.state.birds.length]);
          }return rows;
        }""",BASE)
        self.assertEqual(len(rows),5)
        for r in rows:
            self.assertEqual(r[1:],[1,6400,0])
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate("""async()=>{const p=(await readAll('runnerPlays')).find(p=>p.status==='active'),c=await openRunnerSession(p.profile,p.id,{lifecycle:false});return [c.view.state.stageVersion,c.view.state.goalDistance,c.view.state.birds.length];}"""),[1,6400,0])

    def test_version2_paid_s04_pause_resume_finish_history_scores_and_profiles(self):
        self.assertTrue(self.page.evaluate("""async inputs=>{
          await installPhase();const before=await snapshotAllStores(),p=await buyLegacy({stageId:'S04'});
          if(p.stageVersion!==2||!runnerCanResume(p)||p.snapshot.version!==2||DB_VERSION!==10||BACKUP_VERSION!==10)throw Error('versions');
          let c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();let n=0;const saved=new Set();
          while(c.view.state.mode==='running'){
            const s=c.view.state;
            if(n<inputs.length&&s.elapsed+1e-8>=inputs[n]){await c.jump();n++;}
            await c.advance(1/60);
            const phase=s.supportId!==null&&s.supportId!=='ground'?'platform':s.airAction==='jump'&&s.jumpOriginY===370?'birdJump':null;
            if(phase&&!saved.has(phase)){
              await c.pause();const snap=m.snapshotRunner(c.view.state),centers=c.view.state.birds.map(b=>m.birdCenter(c.view.state,b));
              validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:await snapshotAllStores()});
              c=await openRunnerSession('student',p.id,{lifecycle:false});
              if(JSON.stringify(snap)!==JSON.stringify(m.snapshotRunner(c.view.state))||JSON.stringify(centers)!==JSON.stringify(c.view.state.birds.map(b=>m.birdCenter(c.view.state,b))))throw Error('bird restore');
              await c.resume();saved.add(phase);
            }
          }
          await c.flush();const result=c.view.savedPlay;
          if(result.stageVersion!==2||result.result.reason!=='clear'||result.result.livesRemaining!==2||result.score!==100||saved.size!==2)throw Error('clear');
          const after=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:after});
          if(after.coinSpends.filter(s=>s.id===p.id).length!==1||after.coinSpends.find(s=>s.id===p.id).amount!==30)throw Error('charge');
          for(const name of BACKUP_STORES.filter(x=>!['runnerPlays','coinSpends'].includes(x)))if(JSON.stringify(before[name])!==JSON.stringify(after[name]))throw Error('unrelated store');
          if(JSON.stringify(before.runnerPlays)!==JSON.stringify(after.runnerPlays.filter(r=>r.id!==p.id)))throw Error('history');
          const summary=summarizeRunnerPlays(after.runnerPlays,'student');
          if(summary.bestByStage.S04.score!==100||summary.bestByStageCharacter['S04:shiba'].score!==100||!summary.unlockedStageIds.includes('S05'))throw Error('scores');
          if(JSON.stringify(summarizeRunnerPlays(before.runnerPlays,'test'))!==JSON.stringify(summarizeRunnerPlays(after.runnerPlays,'test')))throw Error('profile');
          return true;
        }""",INPUTS))

    def test_one_hit_clear_is_official_and_keeps_higher_previous_score(self):
        self.assertTrue(self.page.evaluate("""async inputs=>{
          await installPhase();
          const previous=(await readAll('runnerPlays')).find(p=>p.profile==='student'&&p.stageId==='S04');
          previous.score=100;await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').put(previous));
          const p=await buyLegacy({stageId:'S04'}),c=await openRunnerSession('student',p.id,{lifecycle:false});
          await c.resume();let n=0;const plan=inputs.filter((_,i)=>i!==2);
          while(c.view.state.mode==='running'){
            if(n<plan.length&&c.view.state.elapsed+1e-8>=plan[n]){await c.jump();n++;}
            await c.advance(1/60);
          }await c.flush();
          const result=c.view.savedPlay,summary=summarizeRunnerPlays(await readAll('runnerPlays'),'student');
          return result.status==='finished'&&result.result.reason==='clear'&&result.result.livesRemaining===1&&result.score===90&&
            summary.bestByStageCharacter['S04:shiba'].score===100&&summary.bestByStage.S04.score===100&&summary.unlockedStageIds.includes('S05');
        }""",INPUTS))

    def test_s04_v1_v2_active_backup_roundtrip(self):
        self.assertTrue(self.page.evaluate("""async base=>{
          const old=base.states.find(r=>r.phase==='platform').play;await installPhase([old]);
          const fresh=await buyLegacy({profile:'test',stageId:'S04',characterId:'shiba'});
          const c=await openRunnerSession('test',fresh.id,{lifecycle:false});await c.resume();
          for(let f=0;f<830;f++){
            if(f===453||f===720)await c.jump();await c.advance(1/60);
          }await c.pause();
          const d=await snapshotAllStores(),backup=JSON.parse(JSON.stringify({backupFormat:BACKUP_FORMAT,backupVersion:10,data:d}));
          validateBackup(backup);await plushInstall(backup.data);
          if(JSON.stringify(d)!==JSON.stringify(await snapshotAllStores()))throw Error('backup mismatch');
          const v1=await openRunnerSession('student',old.id,{lifecycle:false}),v2=await openRunnerSession('test',fresh.id,{lifecycle:false});
          return v1.view.state.stageVersion===1&&v1.view.state.goalDistance===6400&&v1.view.state.birds.length===0&&v2.view.state.stageVersion===2&&v2.view.state.goalDistance===7000&&v2.view.state.birds.length===3;
        }""",BASE))
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=(await readAll('runnerPlays')).find(p=>p.profile==='test'&&p.status==='active');
          if(!runnerCanResume(p))return false;
          const c=await openRunnerSession('test',p.id,{lifecycle:false});
          return c.view.state.stageVersion===2&&c.view.state.goalDistance===7000&&c.view.state.birds.length===3&&c.view.state.mode==='paused';
        }"""))
