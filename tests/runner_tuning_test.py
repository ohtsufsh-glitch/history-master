"""Issue #85 tuning: version 3 only; frozen v1/v2 checks remain in earlier suites."""
import json
from pathlib import Path
import unittest

import runner_canvas_test as canvas
import runner_phase1_test as phase1

BASE = json.loads((Path(__file__).parent/'fixtures/runner85-tuning-base.json').read_text())
INPUTS = {
    'S02':[4.05,7.55,12,13.75,18.55,22.55],
    'S03':[3,7.55,11.35,15.5,17.1,22.35,24.55,26.85],
    'S04':[4.05,7.55,12,13.95,15.85,17.75,22.55,27,28.55,32.55],
}


class RunnerTuningPhysicsTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    model_runner = canvas.RunnerCanvasTest.model_runner
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    open_runner = canvas.RunnerCanvasTest.open_runner
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    assert_isolated = canvas.RunnerCanvasTest.assert_isolated
    toggle = canvas.RunnerCanvasTest.toggle
    tap = canvas.RunnerCanvasTest.tap

    def model(self):
        p,errors,requests=self.model_runner()
        p.evaluate('()=>{window.trial=('+phase1.TRIAL+');}')
        self.addCleanup(lambda:self.assert_isolated(p,errors,requests))
        return p

    def test_versions_and_unchanged_definitions(self):
        p=self.model()
        self.assertEqual(p.evaluate("runnerModel.STAGES.map(s=>runnerModel.getStage(s.stageId,['S02','S03','S04'].includes(s.stageId)?2:1))"),BASE['stages'])
        self.assertEqual(p.evaluate("runnerModel.STAGES.map(s=>[s.stageId,s.stageVersion??1,s.goalDistance,s.course.filter(e=>e.type==='star').length])"),
                         [['S01',1,4000,10],['S02',3,5000,10],['S03',3,6000,10],['S04',3,7000,10],['S05',1,7200,10],['S06',1,8000,10]])

    def test_shiba_clear_and_missing_required_inputs_at_three_rates(self):
        p=self.model()
        rows=p.evaluate("""plans=>Object.entries(plans).flatMap(([id,inputs])=>[30,60,120].map(hz=>{
          const stage=runnerModel.getStage(id,3),omit={S02:[2,3],S03:[4],S04:[3,4,5]}[id];
          return {id,hz,good:trial(stage,inputs,hz),idle:trial(stage,[],hz),
            omit:trial(stage,inputs.filter((_,i)=>!omit.includes(i)),hz),
            noBlock:trial({...stage,course:stage.course.filter(e=>e.type!=='platform')},inputs,hz)};
        }))""",INPUTS)
        for r in rows:
            self.assertEqual((r['good']['reason'],r['good']['score'],r['good']['lives'],r['good']['hits']),('clear',100,2,0),r)
            self.assertTrue(r['good']['accepted'],r)
            for key in ('idle','omit','noBlock'):
                self.assertEqual((r[key]['reason'],r[key]['lives']),('collision',0),(key,r))
            top={'S02':[3],'S03':[4],'S04':[3,4,5,8]}[r['id']]
            for i in top:
                self.assertNotIn(r['good']['jumps'][i]['support'],(None,'ground'),r)
        print('TUNING: shiba S02/S03/S04 100 points/no hits at 30/60/120Hz; idle/missing chain/no platforms fail')

    def test_input_windows_and_bird_warning(self):
        p=self.model()
        rows=p.evaluate("""plans=>Object.entries(plans).flatMap(([id,inputs])=>inputs.map((_,action)=>{
          let longest=0,streak=0,start,range;
          for(let n=-30;n<=30;n++){
            const r=trial(runnerModel.getStage(id,3),inputs.map((t,i)=>t+(i===action?n/60:0)));
            if(r.reason==='clear'&&r.hits===0&&r.score===100&&r.accepted){
              if(!streak)start=n/60;streak++;if(streak>longest){longest=streak;range=[start,n/60];}
            }else streak=0;
          }return {id,action,range,width:(longest-1)/60};
        }))""",INPUTS)
        for r in rows:
            self.assertGreaterEqual(r['width']+1e-9,.15,r)
        print('TUNING_WINDOWS='+json.dumps(rows))
        warnings=p.evaluate("""plans=>runnerModel.getStage('S04',3).birds.map((b,i)=>
          plans.S04[i+3]-(b.x-(960-186-28))/(200+b.speed))""",INPUTS)
        self.assertGreater(min(warnings),2.5)

    def test_hole_fatal_with_one_two_three_hearts_shield_and_normal_crossing(self):
        p=self.model()
        self.assertTrue(p.evaluate("""()=>{
          const m=runnerModel,stage=m.getStage('S03',3);
          for(const hz of [30,60,120])for(const lives of [1,2,3])for(const shield of [0,1])for(const jump of [false,true])for(const hole of stage.holes){
            const s=m.createRunnerState({...stage,course:[],holes:[hole],goalDistance:hole.end+300},lives===3?'salamander':'shiba');
            s.mode='running';s.lives=lives;let jumped=false,started=false,failed=null;
            while(s.mode==='running'){
              if(!started&&s.distance>=hole.start-100){s.invincibleRemaining=shield;started=true;}
              if(jump&&!jumped&&s.distance>=hole.start-30-1e-6){if(!m.startJump(s))throw Error('input');jumped=true;}
              m.updateRunner(s,1/hz);
              if(s.mode==='finished'&&s.reason==='collision')failed={x:s.distance,y:s.feetY};
            }
            if(jump){if(s.reason!=='clear'||s.lives!==lives)throw Error('false fall');}
            else if(s.reason!=='collision'||s.lives!==0||!failed||failed.y<=470||failed.x>=hole.end)throw Error('fall not immediate');
            const before=JSON.stringify(s);m.updateRunner(s,20);if(m.startJump(s)||JSON.stringify(s)!==before)throw Error('gameover continued');
          }return true;
        }"""))

    def test_each_real_s03_hole_omission_is_fatal_and_old_v2_still_recovers(self):
        p=self.model()
        out=p.evaluate("""plans=>{
          const m=runnerModel,rows=[];
          for(const action of [2,5,7]){
            const r=trial(m.getStage('S03',3),plans.S03.filter((_,i)=>i!==action));rows.push([action,r.reason,r.lives,r.distance]);
          }
          const old=m.createRunnerState(m.getStage('S03',2));old.mode='running';let jumped=false;
          while(old.lives===2){if(!jumped&&old.distance>=1510-1e-6){m.startJump(old);jumped=true;}m.updateRunner(old,1/60);}
          return {rows,old:[old.mode,old.lives,old.supportId,old.distance]};
        }""",INPUTS)
        for (action,reason,lives,x),(start,end) in zip(out['rows'],[(2300,2420),(4500,4630),(5400,5520)]):
            self.assertEqual((reason,lives),('collision',0))
            self.assertGreaterEqual(x,start);self.assertLess(x,end)
        self.assertEqual(out['old'][:3],['running',1,'ground'])
        self.assertGreaterEqual(out['old'][3],2480)

    def test_birds_move_left_and_every_frame_restores_exactly(self):
        p=self.model()
        self.assertTrue(p.evaluate("""plans=>{
          const m=runnerModel;
          for(const version of [2,3]){
            const s=m.createRunnerState(m.getStage('S04',version));s.mode='running';
            const before=m.birdCenter(s,s.birds[0]).x+s.distance;m.updateRunner(s,.25);
            const world=m.birdCenter(s,s.birds[0]).x+s.distance;
            if(Math.abs(world-before-(version===3?-10:0))>1e-7)throw Error('bird world speed');
          }
          for(const id of Object.keys(plans))for(const hit of [false,true]){
            const s=m.createRunnerState(m.getStage(id,3));s.mode='running';let n=0;
            const inputs=hit?(id==='S03'?plans[id].filter((_,i)=>i!==2):plans[id].filter((_,i)=>i!==0)):plans[id];
            for(let f=0;f<2200&&s.mode==='running';f++){
              if(n<inputs.length&&f/60+1e-9>=inputs[n]){m.startJump(s);n++;}m.updateRunner(s,1/60);
              const r=m.restoreRunner({stageId:id,stageVersion:3,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});
              if(JSON.stringify(s.birds.map(b=>m.birdCenter(s,b)))!==JSON.stringify(r.birds.map(b=>m.birdCenter(r,b))))throw Error('bird restore');
              if(r.mode!=='finished'){
                const before=JSON.stringify(r);m.updateRunner(r,100);if(m.startJump(r)||JSON.stringify(r)!==before)throw Error('paused movement');m.resumeRunner(r);
              }
              const copy=structuredClone(s);m.updateRunner(copy,1/60);m.updateRunner(r,1/60);
              if(JSON.stringify(m.snapshotRunner(copy))!==JSON.stringify(m.snapshotRunner(r)))throw Error('trajectory');
            }
          }return true;
        }""",INPUTS))

    def test_real_touch_routes_and_bird_paint_match_collision_at_phone_tablet_sizes(self):
        model=self.model()
        for id in INPUTS:
            stage=model.evaluate('id=>runnerModel.getStage(id,3)',id)
            for width,height in [(390,844),(1024,768)]:
                p,errors,requests=self.manual_runner(course=stage,probe=True,width=width,height=height)
                p.evaluate("""async()=>{
                  window.m=await import(document.querySelector('script[type=module]').src);
                  window.birdPaint=[];const proto=CanvasRenderingContext2D.prototype,arc=proto.arc,transform=proto.setTransform;
                  proto.setTransform=function(...args){birdPaint.length=0;return transform.apply(this,args);};
                  proto.arc=function(x,y,r,...rest){if(this.fillStyle==='#e64b65')birdPaint.push({x,y,r});return arc.call(this,x,y,r,...rest);};
                }""")
                self.toggle(p);p.evaluate('runnerClock.step(0)');now=0
                for i,t in enumerate(INPUTS[id]):
                    p.evaluate('ms=>runnerClock.advance(ms,60)',t*1000-now);self.tap(p);now=t*1000
                    if id=='S04' and i==3:
                        p.evaluate('runnerClock.advance(200,60)');now+=200
                        self.assertTrue(p.evaluate("""()=>{
                          const s=runnerJumpProbe.state,expected=s.birds.map(b=>m.birdCenter(s,b)).filter(b=>b.x+28>=0&&b.x-28<=960);
                          if(!expected.length||expected.length!==birdPaint.length)return false;
                          return expected.every((b,i)=>Math.abs(b.x-birdPaint[i].x)<1e-7&&b.y===birdPaint[i].y&&birdPaint[i].r===26);
                        }"""))
                p.evaluate('ms=>runnerClock.advance(ms,60)',stage['goalDistance']/200*1000+100-now)
                self.assertEqual(p.locator('#runner-result-title').inner_text(),'クリア！')
                self.assertEqual(p.locator('#runner-score').inner_text(),'100')
                self.assert_isolated(p,errors,requests)


class RunnerTuningCompatibilityTest(unittest.TestCase):
    setUpClass = classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass = classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp = phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown = phase1.RunnerPhase1CompatibilityTest.tearDown

    def test_frozen_v2_paid_states_resume_on_original_trajectories(self):
        self.assertTrue(self.page.evaluate("""async base=>{
          for(const {play,next} of base.states){
            await installPhase([play]);const before=await snapshotAllStores();
            if(!runnerCanResume(play)||(await buy({stageId:'S02'})).id!==play.id)throw Error('legacy purchase');
            let c=await openRunnerSession('student',play.id,{lifecycle:false});await c.resume();await c.advance(.1);await c.pause();
            if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(next))throw Error('old trajectory '+play.id);
            c=await openRunnerSession('student',play.id,{lifecycle:false});
            if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(next))throw Error('old save');
            const after=await snapshotAllStores();
            for(const name of BACKUP_STORES.filter(x=>x!=='runnerPlays'))if(JSON.stringify(before[name])!==JSON.stringify(after[name]))throw Error('unrelated store');
            if(JSON.stringify(before.runnerPlays.filter(x=>x.status==='finished'))!==JSON.stringify(after.runnerPlays.filter(x=>x.status==='finished')))throw Error('history');
          }return true;
        }""",BASE))
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate("""async()=>{const p=(await readAll('runnerPlays')).find(p=>p.status==='active'),c=await openRunnerSession(p.profile,p.id,{lifecycle:false});return [c.view.state.stageVersion,c.view.state.goalDistance,c.view.state.birds[0].speed??0];}"""),[2,7000,0])

    def test_v3_purchases_save_reload_and_official_clear_all_three_stages(self):
        for id,inputs in INPUTS.items():
            self.page.evaluate("""async id=>{
              await installPhase();window.paid=await buy({stageId:id});
              if(paid.stageVersion!==3||!runnerCanResume(paid)||paid.snapshot.version!==2||DB_VERSION!==10||BACKUP_VERSION!==10)throw Error('versions');
              let c=await openRunnerSession('student',paid.id,{lifecycle:false});await c.resume();await c.advance(.1);await c.pause();
            }""",id)
            self.page.reload();self.page.wait_for_function('appReady')
            self.assertTrue(self.page.evaluate("""async ({id,inputs})=>{
              const m=await loadRunnerModel(),paid=(await readAll('runnerPlays')).find(p=>p.status==='active');
              if(!runnerCanResume(paid))throw Error('reload not resumable');
              let c=await openRunnerSession('student',paid.id,{lifecycle:false});
              if(c.view.state.stageVersion!==3||c.view.state.mode!=='paused')throw Error('reload version');
              await c.resume();let n=0;const seen=new Set();
              while(c.view.state.mode==='running'){
                const s=c.view.state;if(n<inputs.length&&s.elapsed+1e-8>=inputs[n]){await c.jump();n++;}await c.advance(1/60);
                const phase=s.supportId!==null&&s.supportId!=='ground'?'platform':s.airAction==='jump'&&s.jumpOriginY<470?'topJump':s.invincibleRemaining?'shield':null;
                if(phase&&!seen.has(phase)){
                  await c.pause();const snap=m.snapshotRunner(c.view.state),birds=c.view.state.birds.map(b=>m.birdCenter(c.view.state,b));
                  c=await openRunnerSession('student',paid.id,{lifecycle:false});
                  if(JSON.stringify(snap)!==JSON.stringify(m.snapshotRunner(c.view.state))||JSON.stringify(birds)!==JSON.stringify(c.view.state.birds.map(b=>m.birdCenter(c.view.state,b))))throw Error('saved course');
                  await c.resume();seen.add(phase);
                }
              }await c.flush();
              const result=c.view.savedPlay,d=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:d});
              if(result.status!=='finished'||result.result.reason!=='clear'||result.score!==100||result.result.livesRemaining!==2||result.stageVersion!==3||!seen.has('platform')||!seen.has('topJump'))throw Error('official clear');
              if(d.coinSpends.filter(s=>s.id===paid.id).length!==1||d.coinSpends.find(s=>s.id===paid.id).amount!==30)throw Error('charge');
              const summary=summarizeRunnerPlays(d.runnerPlays,'student');
              if(summary.bestByStage[id].score!==100||summary.bestByStageCharacter[id+':shiba'].score!==100)throw Error('score');
              return true;
            }""",dict(id=id,inputs=inputs)))
            # Next iteration uses the same setup functions; reinstall only the test helpers.
            if id!='S04':
                self.tearDown();self.setUp()

    def test_fatal_hole_formal_gameover_keeps_history_and_stops_progress(self):
        self.assertTrue(self.page.evaluate("""async inputs=>{
          await installPhase();const paid=await buy({stageId:'S03'}),c=await openRunnerSession('student',paid.id,{lifecycle:false});
          const before=await snapshotAllStores();await c.resume();let n=0;const plan=inputs.filter((_,i)=>i!==2);
          while(c.view.state.mode==='running'){
            if(n<plan.length&&c.view.state.elapsed+1e-8>=plan[n]){await c.jump();n++;}await c.advance(1/60);
          }await c.flush();const finished=c.view.savedPlay,snapshot=m.snapshotRunner(c.view.state);
          await c.advance(10);await c.jump();
          const after=await snapshotAllStores();
          if(JSON.stringify(snapshot)!==JSON.stringify(m.snapshotRunner(c.view.state)))throw Error('finished moved');
          if(JSON.stringify(before.runnerPlays.filter(p=>p.id!==paid.id))!==JSON.stringify(after.runnerPlays.filter(p=>p.id!==paid.id)))throw Error('history');
          return finished.status==='finished'&&finished.result.reason==='gameover'&&finished.result.livesRemaining===0&&c.view.state.reason==='collision'&&c.view.state.distance<2420;
        }""",INPUTS['S03']))

    def test_mixed_v2_v3_backup_validate_restore_and_reload_birds(self):
        self.assertTrue(self.page.evaluate("""async ({base,inputs})=>{
          for(const id of ['S02','S03','S04']){
            const old=base.states.find(r=>r.play.stageId===id&&r.phase==='platform').play;
            await installPhase([old]);const fresh=await purchaseRunnerPlay({profile:'test',stageId:id,characterId:'shiba'});
            const c=await openRunnerSession('test',fresh.id,{lifecycle:false});await c.resume();let n=0;
            while(c.view.state.elapsed<13.5){
              if(n<inputs[id].length&&c.view.state.elapsed+1e-8>=inputs[id][n]){await c.jump();n++;}await c.advance(1/60);
            }await c.pause();
            const data=await snapshotAllStores(),backup=JSON.parse(JSON.stringify({backupFormat:BACKUP_FORMAT,backupVersion:10,data}));
            validateBackup(backup);await plushInstall(backup.data);
            if(JSON.stringify(data)!==JSON.stringify(await snapshotAllStores()))throw Error('backup values');
            for(const [profile,p,version] of [['student',old,2],['test',fresh,3]]){
              const session=await openRunnerSession(profile,p.id,{lifecycle:false});
              if(session.view.state.stageVersion!==version||session.view.state.goalDistance!==m.getStage(id,version).goalDistance)throw Error('backup version');
            }
          }return true;
        }""",dict(base=BASE,inputs=INPUTS)))
        probe="""async()=>{
          const m=await loadRunnerModel(),p=(await readAll('runnerPlays')).find(p=>p.profile==='test'&&p.status==='active');
          const c=await openRunnerSession('test',p.id,{lifecycle:false}),s=c.view.state;
          if(s.stageVersion!==3||!s.birds.every(b=>b.speed===40)||s.mode!=='paused')throw Error('reload state');
          return {snapshot:m.snapshotRunner(s),birds:s.birds.map(b=>m.birdCenter(s,b))};
        }"""
        saved=self.page.evaluate(probe)
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate(probe),saved)
