"""Issue #85 density: latest courses, single-jump routes and paid-play compatibility."""
import json
from pathlib import Path
import unittest

import runner_canvas_test as canvas
import runner_phase1_test as phase1
from runner_extension_cases import INPUTS as VERTICAL_INPUTS

BASE = json.loads((Path(__file__).parent/'fixtures/runner85-density-base.json').read_text())
INPUTS = {
    "S01": [
        3.55,
        5.55,
        7.55,
        10.05,
        13.05,
        16.05
    ],
    "S02": [
        1.65,
        2.75,
        3.85,
        4.95,
        6.05,
        7.15,
        8.3,
        10.05,
        12.25,
        13.35,
        14.45,
        15.55,
        16.7,
        18.45,
        20.65,
        21.75,
        22.85,
        23.95
    ],
    "S03": [
        1.95,
        3.05,
        4.15,
        5.25,
        6.35,
        7.45,
        8.55,
        10.3,
        11.35,
        13.85,
        14.95,
        16.05,
        17.15,
        18.25,
        19.35,
        20.35,
        21.8,
        22.85,
        25.25,
        26.45,
        27.65,
        28.85
    ],
    "S04": [
        1.65,
        2.7,
        3.75,
        4.8,
        5.85,
        6.9,
        7.95,
        9,
        10.45,
        11.65,
        12.85,
        15.45,
        16.5,
        17.55,
        18.6,
        19.65,
        20.7,
        21.75,
        22.8,
        24.25,
        25.45,
        26.65,
        28.95,
        30,
        31.05,
        32.1,
        33.15,
        34.2
    ],
    "S05": [
        1.65,
        2.95,
        4.25,
        5.825,
        6.65,
        7.7,
        8.8,
        10.55,
        12.3,
        14.05,
        15.8,
        17.55,
        19.3,
        21.05,
        22.8,
        24.55,
        26.3,
        28.05,
        29.8,
        31.55
    ],
    "S06": [
        1.65,
        2.85,
        4.05,
        5.825,
        6.65,
        7.7,
        8.85,
        9.85,
        11.35,
        12.65,
        13.95,
        15.25,
        16.55,
        17.85,
        19.15,
        20.45,
        21.75,
        23.05,
        24.35,
        25.65,
        26.95,
        28.25,
        29.55,
        30.85,
        32.15,
        33.45
    ]
}

LATEST_INPUTS = {**INPUTS, **VERTICAL_INPUTS}


TRIAL = """(stage,inputs,hz=60)=>{
 const s=runnerModel.createRunnerState(stage);s.mode='running';let n=0;const hits=[],jumps=[],landings=[];
 for(let f=0;f<hz*45&&s.mode==='running';f++){
 if(n<inputs.length&&f/hz+1e-9>=inputs[n]){const support=s.supportId;jumps.push({t:s.elapsed,support,ok:runnerModel.startJump(s)});n++;}
 const lives=s.lives,old=s.supportId;runnerModel.updateRunner(s,1/hz);
 if(lives>s.lives)hits.push({t:s.elapsed,x:s.distance,y:s.feetY});
 if(s.supportId!==null&&s.supportId!=='ground'&&old!==s.supportId)landings.push({t:s.elapsed,x:s.distance,id:s.supportId});
 }
 return {reason:s.reason,score:s.score,lives:s.lives,hits,jumps,landings};
}"""

class RunnerDensityPhysicsTest(unittest.TestCase):
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
        p.evaluate('()=>{window.runnerModel={...runnerModel,STAGES:runnerModel.STAGES.map(s=>runnerModel.getStage(s.stageId,["S02","S03","S04"].includes(s.stageId)?4:2))};window.trial=('+TRIAL+');}')
        self.addCleanup(lambda:self.assert_isolated(p,errors,requests))
        return p

    def test_versions_density_and_legacy_definitions(self):
        p=self.model()
        self.assertEqual(p.evaluate("runnerModel.STAGES.map(s=>runnerModel.getStage(s.stageId,['S02','S03','S04'].includes(s.stageId)?3:1))"),BASE['stages'])
        self.assertEqual(p.evaluate("runnerModel.STAGES.map(s=>[s.stageVersion,s.goalDistance,s.course.filter(e=>e.type==='star').length,s.course.filter(e=>['obstacle','wall'].includes(e.type)).length+s.holes.length+s.birds.length])"),
          [[2,4000,10,6],[4,5000,10,18],[4,6000,10,20],[4,7000,10,28],[2,7200,10,18],[2,8000,10,24]])

    def test_routes_and_sequential_landings_at_three_rates(self):
        p=self.model()
        rows=p.evaluate("""plans=>runnerModel.STAGES.flatMap(stage=>[30,60,120].map(hz=>({id:stage.stageId,hz,
          good:trial(stage,plans[stage.stageId],hz),idle:trial(stage,[],hz)})))""",INPUTS)
        for r in rows:
            g=r['good']
            self.assertEqual((g['reason'],g['score'],g['lives'],len(g['hits'])),('clear',100,2,0),r)
            self.assertTrue(all(j['ok'] for j in g['jumps']),r)
            self.assertEqual(r['idle']['reason'],'collision',r)
            if r['id'] in ('S05','S06'):
                self.assertEqual(len(g['landings']),3 if r['id']=='S05' else 4,r)
                self.assertEqual([j['support'] for j in g['jumps'][4:7 if r['id']=='S05' else 8]], [l['id'] for l in g['landings']],r)
        print('Density: all six shiba routes 100 points / no hits at 30, 60, 120Hz')

    def test_missing_chain_jumps_hit_visible_ground_wall(self):
        p=self.model()
        rows=p.evaluate("""plans=>['S05','S06'].flatMap(id=>{
          const stage=runnerModel.STAGES.find(s=>s.stageId===id),inputs=plans[id];
          return inputs.map((t,i)=>({t,i})).filter(a=>a.t>6&&a.t<10).map(a=>({id,...a,
            result:trial(stage,inputs.filter((_,i)=>i!==a.i))}));
        })""",INPUTS)
        for r in rows:
            self.assertGreater(len(r['result']['hits']),0,r)
            self.assertTrue(any(h['x']>=1280 and h['x']<=2110 for h in r['result']['hits']),r)
        print('Chain omissions: every omitted re-jump causes a hit')

    def test_whole_chain_omission_and_ground_bypass_fail(self):
        p=self.model()
        rows=p.evaluate("""plans=>['S05','S06'].map(id=>{
          const stage=runnerModel.STAGES.find(s=>s.stageId===id),inputs=plans[id];
          return {id,skip:trial(stage,inputs.filter(t=>t<6||t>10)),
            ground:trial({...stage,course:stage.course.filter(e=>e.type!=='platform')},inputs),
            falls:inputs.filter(t=>t>6&&t<10).map(t=>trial({...stage,birds:[]},inputs.filter(x=>x!==t)))};
        })""",INPUTS)
        for r in rows:
            self.assertEqual(r['skip']['reason'],'collision',r)
            self.assertEqual(r['ground']['reason'],'collision',r)
            for fall in r['falls']:
                self.assertTrue(any(1280<=h['x']<=2110 for h in fall['hits']),r)

    def test_deck_bird_jumps_require_platform_support(self):
        p=self.model()
        rows=p.evaluate("""plans=>['S02','S04'].map(id=>{
          const stage=runnerModel.STAGES.find(s=>s.stageId===id),inputs=plans[id],
            indices=id==='S02'?[7,13]:[8,9,10,19,20,21];
          return {id,good:trial(stage,inputs),indices,
            skip:trial(stage,inputs.filter((_,i)=>!indices.includes(i))),
            ground:trial({...stage,course:stage.course.filter(e=>e.type!=='platform')},inputs),
            singles:indices.map(index=>trial(stage,inputs.filter((_,i)=>i!==index)))};
        })""",INPUTS)
        for r in rows:
            for i in r['indices']:self.assertNotIn(r['good']['jumps'][i]['support'],(None,'ground'))
            self.assertEqual(r['skip']['reason'],'collision',r)
            self.assertEqual(r['ground']['reason'],'collision',r)
            for single in r['singles']:self.assertGreater(len(single['hits']),0)

    def test_measured_input_windows_and_bird_warning(self):
        p=self.model()
        rows=p.evaluate("""plans=>runnerModel.STAGES.flatMap(stage=>plans[stage.stageId].map((t,action)=>{
          const inputs=plans[stage.stageId];let longest=0,streak=0,start,range;
          for(let n=-24;n<=24;n++){
            const r=trial(stage,inputs.map((t,i)=>t+(i===action?n/60:0)));
            if(r.reason==='clear'&&!r.hits.length&&r.score===100&&r.jumps.every(j=>j.ok)){
              if(!streak)start=n/60;streak++;if(streak>longest){longest=streak;range=[t+start,t+n/60];}
            }else streak=0;
          }return {id:stage.stageId,action,t,range,width:(longest-1)/60};
        }))""",INPUTS)
        for r in rows:self.assertGreaterEqual(r['width']+1e-9,.15,r)
        print('Input windows: minimum', min(r['width'] for r in rows), 'seconds')
        warnings=p.evaluate("""()=>runnerModel.STAGES.flatMap(s=>s.birds.map(b=>
          (b.x/320-.45)-(b.x-(960-186-28))/320))""")
        self.assertGreater(min(warnings),1.8)

    def test_hole_fatal_with_one_two_three_hearts_shield_and_normal_crossing(self):
        p=self.model()
        self.assertTrue(p.evaluate("""()=>{
          const m=runnerModel,stage=m.getStage('S03',4);
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

    def test_birds_move_left_and_every_frame_restores_exactly(self):
        p=self.model()
        self.assertTrue(p.evaluate("""plans=>{
          const m=runnerModel;
          for(const version of [2,3,4]){
            const s=m.createRunnerState(m.getStage('S04',version));s.mode='running';
            const before=m.birdCenter(s,s.birds[0]).x+s.distance;m.updateRunner(s,.25);
            const world=m.birdCenter(s,s.birds[0]).x+s.distance;
            if(Math.abs(world-before-(version===4?-30:version===3?-10:0))>1e-7)throw Error('bird world speed');
          }
          for(const id of Object.keys(plans))for(const hit of [false,true]){
            const s=m.createRunnerState(m.STAGES.find(s=>s.stageId===id));s.mode='running';let n=0;
            const inputs=hit?(id==='S03'?plans[id].filter((_,i)=>i!==0):plans[id].filter((_,i)=>i!==0)):plans[id];
            for(let f=0;f<2200&&s.mode==='running';f++){
              if(n<inputs.length&&f/60+1e-9>=inputs[n]){m.startJump(s);n++;}m.updateRunner(s,1/60);
              const r=m.restoreRunner({stageId:id,stageVersion:s.stageVersion,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});
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
            stage=model.evaluate('id=>runnerModel.STAGES.find(s=>s.stageId===id)',id)
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
                    if id=='S04' and i==8:
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




class RunnerDensityCompatibilityTest(unittest.TestCase):
    setUpClass = classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass = classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    # Historical purchased records must continue on the density versions.
    def setUp(self):
        phase1.RunnerPhase1CompatibilityTest.setUp(self)
        self.page.evaluate("""()=>{window.buy=async({stageId='S01'}={})=>{
          const active=(await readAll('runnerPlays')).find(p=>p.profile==='student'&&p.status==='active');if(active)return active;
          const stage=m.getStage(stageId,['S02','S03','S04'].includes(stageId)?4:2),at=new Date().toISOString();
          const p={id:crypto.randomUUID(),profile:'student',game:'runner',schemaVersion:1,stageId,stageVersion:stage.stageVersion,characterId:'shiba',
            startedAt:at,updatedAt:at,status:'active',score:0,snapshot:m.snapshotRunner(m.createRunnerState(stage))};
          await runnerTransaction(['runnerPlays','coinSpends'],tx=>{tx.objectStore('runnerPlays').add(p);tx.objectStore('coinSpends').add({id:p.id,profile:'student',game:'runner',amount:30,at});});return p;
        };}""")
    tearDown = phase1.RunnerPhase1CompatibilityTest.tearDown

    def test_frozen_previous_paid_states_resume_on_original_trajectories(self):
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
        self.assertEqual(self.page.evaluate("""async()=>{const p=(await readAll('runnerPlays')).find(p=>p.status==='active'),c=await openRunnerSession(p.profile,p.id,{lifecycle:false});return [c.view.state.stageVersion,c.view.state.goalDistance,c.view.state.birds[0]?.speed??0];}"""),[1,8000,0])

    def test_density_paid_records_save_reload_and_official_clear_all_six_stages(self):
        for id,inputs in INPUTS.items():
            self.page.evaluate("""async id=>{
              await installPhase();window.paid=await buy({stageId:id});
              if(paid.stageVersion!==(['S02','S03','S04'].includes(id)?4:2)||!runnerCanResume(paid)||paid.snapshot.version!==2||DB_VERSION!==10||BACKUP_VERSION!==10)throw Error('versions');
              let c=await openRunnerSession('student',paid.id,{lifecycle:false});await c.resume();await c.advance(.1);await c.pause();
            }""",id)
            self.page.reload();self.page.wait_for_function('appReady')
            self.assertTrue(self.page.evaluate("""async ({id,inputs})=>{
              const m=await loadRunnerModel(),paid=(await readAll('runnerPlays')).find(p=>p.status==='active');
              if(!runnerCanResume(paid))throw Error('reload not resumable');
              let c=await openRunnerSession('student',paid.id,{lifecycle:false});
              if(c.view.state.stageVersion!==(['S02','S03','S04'].includes(id)?4:2)||c.view.state.mode!=='paused')throw Error('reload version');
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
              if(result.status!=='finished'||result.result.reason!=='clear'||result.score!==100||result.result.livesRemaining!==2||result.stageVersion!==(['S02','S03','S04'].includes(id)?4:2)||(id!=='S01'&&(!seen.has('platform')||!seen.has('topJump'))))throw Error('official clear');
              if(d.coinSpends.filter(s=>s.id===paid.id).length!==1||d.coinSpends.find(s=>s.id===paid.id).amount!==30)throw Error('charge');
              const summary=summarizeRunnerPlays(d.runnerPlays,'student');
              if(summary.bestByStage[id].score!==100||summary.bestByStageCharacter[id+':shiba'].score!==100)throw Error('score');
              return true;
            }""",dict(id=id,inputs=inputs)))
            # Next iteration uses the same setup functions; reinstall only the test helpers.
            if id!='S06':
                self.tearDown();self.setUp()

    def test_fatal_hole_formal_gameover_keeps_history_and_stops_progress(self):
        self.assertTrue(self.page.evaluate("""async inputs=>{
          await installPhase();const paid=await buy({stageId:'S03'}),c=await openRunnerSession('student',paid.id,{lifecycle:false});
          const before=await snapshotAllStores();await c.resume();let n=0;const plan=inputs.filter((_,i)=>i!==0);
          while(c.view.state.mode==='running'){
            if(n<plan.length&&c.view.state.elapsed+1e-8>=plan[n]){await c.jump();n++;}await c.advance(1/60);
          }await c.flush();const finished=c.view.savedPlay,snapshot=m.snapshotRunner(c.view.state);
          await c.advance(10);await c.jump();
          const after=await snapshotAllStores();
          if(JSON.stringify(snapshot)!==JSON.stringify(m.snapshotRunner(c.view.state)))throw Error('finished moved');
          if(JSON.stringify(before.runnerPlays.filter(p=>p.id!==paid.id))!==JSON.stringify(after.runnerPlays.filter(p=>p.id!==paid.id)))throw Error('history');
          return finished.status==='finished'&&finished.result.reason==='gameover'&&finished.result.livesRemaining===0&&c.view.state.reason==='collision'&&c.view.state.distance<520;
        }""",INPUTS['S03']))

    def test_mixed_previous_latest_backup_validate_restore_and_reload_birds(self):
        self.assertTrue(self.page.evaluate("""async ({base,inputs})=>{
          for(const id of Object.keys(inputs)){
            const old=base.states.find(r=>r.play.stageId===id&&r.play.snapshot.elapsed>1).play;
            await installPhase([old]);const fresh=await purchaseRunnerPlay({profile:'test',stageId:id,characterId:'shiba'});
            const c=await openRunnerSession('test',fresh.id,{lifecycle:false});await c.resume();let n=0;
            while(c.view.state.elapsed<13.5){
              if(n<inputs[id].length&&c.view.state.elapsed+1e-8>=inputs[id][n]){await c.jump();n++;}await c.advance(1/60);
            }await c.pause();
            const data=await snapshotAllStores(),backup=JSON.parse(JSON.stringify({backupFormat:BACKUP_FORMAT,backupVersion:10,data}));
            validateBackup(backup);await plushInstall(backup.data);
            if(JSON.stringify(data)!==JSON.stringify(await snapshotAllStores()))throw Error('backup values');
            for(const [profile,p,version] of [['student',old,old.stageVersion],['test',fresh,fresh.stageVersion]]){
              const session=await openRunnerSession(profile,p.id,{lifecycle:false});
              if(session.view.state.stageVersion!==version||session.view.state.goalDistance!==m.getStage(id,version).goalDistance)throw Error('backup version');
            }
          }return true;
        }""",dict(base=BASE,inputs=LATEST_INPUTS)))
        probe="""async()=>{
          const m=await loadRunnerModel(),p=(await readAll('runnerPlays')).find(p=>p.profile==='test'&&p.status==='active');
          const c=await openRunnerSession('test',p.id,{lifecycle:false}),s=c.view.state;
          if(s.stageVersion!==8||!s.birds.every(b=>b.speed===120)||s.mode!=='paused')throw Error('reload state');
          return {snapshot:m.snapshotRunner(s),birds:s.birds.map(b=>m.birdCenter(s,b))};
        }"""
        saved=self.page.evaluate(probe)
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate(probe),saved)

class RunnerDensityFormalInputTest(unittest.TestCase):
    setUpClass = classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass = classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp = phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown = phase1.RunnerPhase1CompatibilityTest.tearDown

    def test_formal_buttons_all_six_and_representative_captures(self):
        import os
        self.context.add_init_script(canvas.MANUAL_FRAMES)
        for id,inputs in LATEST_INPUTS.items():
            width,height=(390,844) if id in ('S01','S03','S05') else (1024,768)
            self.page.set_viewport_size(dict(width=width,height=height))
            self.page.evaluate("async()=>{await navigate('home','student');await installPhase();}")
            self.page.locator('#open-runner').click()
            self.page.locator(f'#formal-stage-cards [data-choice="{id}"]').click()
            frame=self.page.frame_locator('iframe')
            frame.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
            frame.locator('body').evaluate('()=>runnerClock.step(0)')
            frame.locator('#runner-toggle').click()
            self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
            frame.locator('body').evaluate('()=>runnerClock.step(0)')
            for i,t in enumerate(inputs):
                self.page.evaluate("""async t=>{
                  const c=formalRunner.session;
                  while(c.view.state.elapsed<t-1e-9)await formalRunner.bridge.advance(Math.min(1/60,t-c.view.state.elapsed));
                }""",t)
                frame.locator('#runner-jump').dispatch_event('pointerdown',dict(pointerType='touch',isPrimary=True,button=0))
                self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
                if id in ('S05','S06') and i==4:
                    self.page.evaluate("async()=>{await formalRunner.bridge.advance(.2);}")
                    frame.locator('body').evaluate('()=>runnerClock.step(0)')
                    if os.environ.get('RUNNER_CAPTURE'):
                        folder=Path('docs/screenshots/runner-85-density');folder.mkdir(parents=True,exist_ok=True)
                        self.page.screenshot(path=str(folder/f'{id.lower()}-{"iphone" if width==390 else "ipad"}.png'))
            self.page.evaluate("""async()=>{
              while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(1/60);
              await formalRunner.session.flush();
            }""")
            frame.locator('body').evaluate('()=>runnerClock.step(0)')
            self.assertEqual(frame.locator('#runner-result-title').inner_text(),'クリア！')
            self.assertEqual(self.page.evaluate("[formalRunner.session.view.savedPlay.score,formalRunner.session.view.savedPlay.result.livesRemaining]"),[100,2])
            self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).filter(s=>s.id===formalRunner.session.view.savedPlay.id).map(s=>s.amount)"),[30])
