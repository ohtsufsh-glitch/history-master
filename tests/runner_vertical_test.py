"""Issue #85 vertical hazards: targeted physics, branches, paid persistence."""
import json
from pathlib import Path
import unittest
import runner_canvas_test as canvas
import runner_phase1_test as phase1
from runner_vertical_cases import INPUTS, UPPER
BASE = json.loads((Path(__file__).parent/'fixtures/runner85-vertical-base.json').read_text())

class RunnerVerticalCompatibilityTest(unittest.TestCase):
    setUpClass = classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass = classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp = phase1.RunnerPhase1CompatibilityTest.setUp
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
        self.assertEqual(self.page.evaluate("""async()=>{const p=(await readAll('runnerPlays')).find(p=>p.status==='active'),c=await openRunnerSession(p.profile,p.id,{lifecycle:false});return [c.view.state.stageVersion,c.view.state.goalDistance,c.view.state.birds[0]?.speed??0];}"""),[2,8000,120])

    def test_latest_purchases_save_reload_and_official_clear_three_stages(self):
        for id,inputs in INPUTS.items():
            self.page.evaluate("""async id=>{
              await installPhase();window.paid=await buy({stageId:id});
              if(paid.stageVersion!==(id==='S04'?5:3)||!runnerCanResume(paid)||paid.snapshot.version!==2||DB_VERSION!==10||BACKUP_VERSION!==10)throw Error('versions');
              let c=await openRunnerSession('student',paid.id,{lifecycle:false});await c.resume();await c.advance(.1);await c.pause();
            }""",id)
            self.page.reload();self.page.wait_for_function('appReady')
            self.assertTrue(self.page.evaluate("""async ({id,inputs})=>{
              const m=await loadRunnerModel(),paid=(await readAll('runnerPlays')).find(p=>p.status==='active');
              if(!runnerCanResume(paid))throw Error('reload not resumable');
              let c=await openRunnerSession('student',paid.id,{lifecycle:false});
              if(c.view.state.stageVersion!==(id==='S04'?5:3)||c.view.state.mode!=='paused')throw Error('reload version');
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
              if(result.status!=='finished'||result.result.reason!=='clear'||result.score!==100||result.result.livesRemaining!==2||result.stageVersion!==(id==='S04'?5:3)||(id!=='S01'&&(!seen.has('platform')||!seen.has('topJump'))))throw Error('official clear '+JSON.stringify({id,result,seen:[...seen]}));
              if(d.coinSpends.filter(s=>s.id===paid.id).length!==1||d.coinSpends.find(s=>s.id===paid.id).amount!==30)throw Error('charge');
              const summary=summarizeRunnerPlays(d.runnerPlays,'student');
              if(summary.bestByStage[id].score!==100||summary.bestByStageCharacter[id+':shiba'].score!==100)throw Error('score');
              return true;
            }""",dict(id=id,inputs=inputs)))
            # Next iteration uses the same setup functions; reinstall only the test helpers.
            if id!='S06':
                self.tearDown();self.setUp()

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
        }""",dict(base=BASE,inputs=INPUTS)))
        probe="""async()=>{
          const m=await loadRunnerModel(),p=(await readAll('runnerPlays')).find(p=>p.profile==='test'&&p.status==='active');
          const c=await openRunnerSession('test',p.id,{lifecycle:false}),s=c.view.state;
          if(s.stageVersion!==3||!s.birds.every(b=>b.speed===120)||s.mode!=='paused')throw Error('reload state');
          return {snapshot:m.snapshotRunner(s),birds:s.birds.map(b=>m.birdCenter(s,b)),spikes:s.spikes.map(b=>m.spikeCenter(s,b))};
        }"""
        saved=self.page.evaluate(probe)
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate(probe),saved)


TRIAL = """(stage,inputs,hz=60)=>{
 const m=runnerModel,s=m.createRunnerState(stage);s.mode='running';let n=0,minY=999;const hits=[],jumps=[],landings=[];
 for(let f=0;f<hz*45&&s.mode==='running';f++){
  if(n<inputs.length&&f/hz+1e-9>=inputs[n]){const support=s.supportId;jumps.push({t:s.elapsed,support,ok:m.startJump(s)});n++;}
  const lives=s.lives,old=s.supportId;m.updateRunner(s,1/hz);minY=Math.min(minY,s.feetY-91);
  if(lives>s.lives)hits.push({t:s.elapsed,x:s.distance,birds:s.birds.filter(b=>m.touchesBird(s,b)).map(b=>b.x/1.6)});
  if(s.supportId!==null&&s.supportId!=='ground'&&old!==s.supportId)landings.push({t:s.elapsed,x:s.distance,height:470-s.feetY});
 }
 return {reason:s.reason,score:s.score,lives:s.lives,hits,jumps,landings,minY};
}"""

class RunnerVerticalPhysicsTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    model_runner = canvas.RunnerCanvasTest.model_runner
    open_runner = canvas.RunnerCanvasTest.open_runner
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    assert_isolated = canvas.RunnerCanvasTest.assert_isolated

    def model(self):
        p,errors,requests=self.model_runner()
        p.evaluate('()=>{window.trial=('+TRIAL+');}')
        self.addCleanup(lambda:self.assert_isolated(p,errors,requests))
        return p

    def test_frozen_definitions_latest_counts_and_late_bird_distribution(self):
        p=self.model()
        self.assertEqual(p.evaluate("""()=>runnerModel.STAGES.flatMap(s=>[1,2,3,4].map(v=>runnerModel.getStage(s.stageId,v)).filter(Boolean)).filter(s=>!['S05','S06'].includes(s.stageId)||s.stageVersion!==3)"""),BASE['stages'])
        rows=p.evaluate("""()=>runnerModel.STAGES.slice(3).map(s=>({id:s.stageId,v:s.stageVersion,length:s.goalDistance,
          stars:s.course.filter(e=>e.type==='star').length,birds:s.birds.length,spikes:s.spikes.length,
          half:s.birds.filter(b=>b.x/1.6>=s.goalDistance/2).length,third:s.birds.filter(b=>b.x/1.6>=s.goalDistance*2/3).length,
          speeds:s.birds.map(b=>b.speed)}))""")
        for r,expected in zip(rows,[(5,7000,8,2),(3,7200,12,4),(3,8000,16,5)]):
            self.assertEqual((r['v'],r['length'],r['birds'],r['spikes']),expected)
            self.assertEqual(r['stars'],10);self.assertEqual(set(r['speeds']),{120})
        self.assertGreaterEqual(rows[1]['half'],7);self.assertGreaterEqual(rows[1]['third'],5)
        self.assertGreaterEqual(rows[2]['half'],10);self.assertGreaterEqual(rows[2]['third'],6)

    def test_lower_routes_three_rates_high_ascent_descent_and_display_bounds(self):
        p=self.model()
        rows=p.evaluate("""plans=>Object.entries(plans).flatMap(([id,inputs])=>[30,60,120].map(hz=>({id,hz,
          result:trial(runnerModel.STAGES.find(s=>s.stageId===id),inputs,hz)})))""",INPUTS)
        for r in rows:
            g=r['result'];self.assertEqual((g['reason'],g['score'],g['lives'],g['hits']),('clear',100,2,[]),r)
            self.assertTrue(all(j['ok'] for j in g['jumps']),r);self.assertGreaterEqual(g['minY'],48,r)
            ascending={'S04':[80,150],'S05':[80,150,200],'S06':[80,140,185,210]}[r['id']]
            high=[l['height'] for l in g['landings'] if 2400<l['x']<4050]
            self.assertTrue(all(h in high for h in ascending),r)
            self.assertIn(80 if r['id']=='S04' else 70,high[high.index(max(ascending))+1:],r)
        # All ordinary character jump apexes at the highest platform leave image headroom.
        self.assertTrue(p.evaluate("""()=>runnerModel.STAGES.slice(3).every(s=>{
          const height=Math.max(...s.course.filter(e=>e.type==='platform').map(e=>e.height));
          return runnerModel.CHARACTERS.every(c=>470-height-c.jump.height-100*c.image.feetRatio>=0)&&
            s.birds.every(b=>470-b.height-28>=0)&&s.spikes.every(b=>470-b.height-b.amplitude-26>=0);
        })"""))

    def test_upper_routes_are_selected_by_jumps_and_s06_trap_keeps_physics(self):
        p=self.model()
        rows=p.evaluate("""plans=>Object.entries(plans).flatMap(([id,inputs])=>[30,60,120].map(hz=>({id,hz,
          r:trial(runnerModel.STAGES.find(s=>s.stageId===id),inputs,hz)})))""",UPPER)
        for row in rows:
            r=row['r'];self.assertEqual((r['reason'],r['score'],r['lives']),('clear',100,1 if row['id']=='S06' else 2),row)
            self.assertTrue(all(j['ok'] for j in r['jumps']),row)
            start,end=(3900,4600) if row['id']=='S05' else (4200,5100)
            self.assertTrue(any(start<l['x']<end and l['height']==150 for l in r['landings']),row)
            if row['id']=='S06':self.assertTrue(any(4520 in h['birds'] for h in r['hits']),row)
        lows=p.evaluate("""plans=>['S05','S06'].map(id=>trial(runnerModel.STAGES.find(s=>s.stageId===id),plans[id]))""",INPUTS)
        for id,r in zip(['S05','S06'],lows):
            start,end=(3900,4600) if id=='S05' else (4200,5100)
            self.assertFalse(any(start<l['x']<end and l['height']==150 for l in r['landings']))

    def test_trap_multiple_entry_and_rejump_patterns(self):
        p=self.model()
        r=p.evaluate("""plans=>{
          const stage=runnerModel.getStage('S06',3);let total=0,entered=0,minimum=9;
          for(let ai=0;ai<8;ai++)for(let bi=0;bi<9;bi++){
            const a=20.2+ai/10,b=21.2+bi/10;
            const variants=[[],...Array.from({length:16},(_,i)=>[21.9+i*.1]),
              ...Array.from({length:7},(_,i)=>[21.9+i*.1,22.9+i*.1])];
            for(const extra of variants){
              const inputs=plans.filter(t=>t!==26.8).concat([a,b,26.95],extra).sort((a,b)=>a-b);
              const r=trial(stage,inputs);total++;
              if(!r.landings.some(l=>l.height===150&&l.x>4300&&l.x<5000))continue;
              entered++;minimum=Math.min(minimum,r.hits.filter(h=>h.birds.some(x=>x>=4520&&x<=4670)).length);
            }
          }return {total,entered,minimum};
        }""",INPUTS['S06'])
        self.assertEqual(r['total'],1728);self.assertGreater(r['entered'],700);self.assertGreaterEqual(r['minimum'],1)
        print('Trap sampling (not a proof of impossibility):',r)

    def test_major_jump_windows(self):
        p=self.model()
        rows=p.evaluate("""plans=>Object.entries(plans).flatMap(([id,inputs])=>inputs.map((t,i)=>{
          const stage=runnerModel.STAGES.find(s=>s.stageId===id);let best=0,streak=0,start,range;
          for(let n=-24;n<=24;n++){
            const r=trial(stage,inputs.map((x,j)=>x+(i===j?n/60:0)));
            if(r.reason==='clear'&&r.lives===2&&r.score===100&&r.jumps.every(j=>j.ok)&&
              r.landings.some(l=>l.height===({S04:150,S05:200,S06:210})[id])){
              if(!streak)start=t+n/60;streak++;if(streak>best){best=streak;range=[start,t+n/60];}
            }else streak=0;
          }return {id,t,width:(best-1)/60,range};
        }))""",INPUTS)
        for r in rows:self.assertGreaterEqual(r['width']+1e-8,.2,r)
        print('Jump windows:',json.dumps(rows))

    def test_motion_collision_and_canvas_share_positions(self):
        p=self.model()
        self.assertTrue(p.evaluate("""()=>{
          const m=runnerModel,s=m.createRunnerState(m.getStage('S06',3));s.mode='running';
          for(const spike of s.spikes){
            const initial=m.spikeCenter(s,spike);s.elapsed=spike.period;
            const loop=m.spikeCenter(s,spike);if(Math.hypot(initial.x-loop.x,initial.y-loop.y)>1e-8)throw Error('period');
            s.elapsed=1.27;s.distance=spike.x;
            const center=m.spikeCenter(s,spike);s.supportId=null;s.feetY=center.y+43;
            if(!m.touchesSpike(s,spike))throw Error('center collision');
            s.feetY=center.y+43+54.001;if(m.touchesSpike(s,spike))throw Error('outside collision');
            s.feetY=center.y+43+53.999;if(!m.touchesSpike(s,spike))throw Error('inside collision');
            // Read actual Canvas path vertices and bounding radius.
            const points=[],ctx={save(){},restore(){},beginPath(){},closePath(){},fill(){},stroke(){},arc(){},
              moveTo(x,y){points.push({x,y})},lineTo(x,y){points.push({x,y})}};
            s.distance=spike.x; m.drawSpike(ctx,s,spike);
            if(points.length!==24||points.some(p=>Math.hypot(p.x-center.x,p.y-center.y)>26.001))throw Error('spike paint');
            s.elapsed=0;s.distance=0;
          }
          const bird=s.birds[0],before=m.birdCenter(s,bird);m.updateRunner(s,.25);
          const after=m.birdCenter(s,bird);
          if(Math.abs(after.x+s.distance-before.x+30)>1e-7)throw Error('120 speed');
          s.distance=bird.x-120*s.elapsed;s.supportId=null;s.feetY=470-bird.height+43;
          if(!m.touchesBird(s,bird))throw Error('bird center');s.feetY+=56.001;
          if(m.touchesBird(s,bird))throw Error('bird outside');
          return true;
        }"""))

    def test_every_frame_pause_restore_next_step_same_including_hit(self):
        p=self.model()
        self.assertTrue(p.evaluate("""({plans,upper})=>{
          const m=runnerModel;
          for(const [id,inputs] of [...Object.entries(plans),['S06',upper.S06]]){
            const s=m.createRunnerState(m.STAGES.find(s=>s.stageId===id));s.mode='running';let n=0;
            while(s.mode==='running'){
              if(n<inputs.length&&s.elapsed+1e-8>=inputs[n]){m.startJump(s);n++;}m.updateRunner(s,1/60);
              const r=m.restoreRunner({stageId:id,stageVersion:s.stageVersion,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});
              const positions=s=>JSON.stringify([s.spikes.map(b=>m.spikeCenter(s,b)),s.birds.map(b=>m.birdCenter(s,b))]);
              if(positions(s)!==positions(r))throw Error('restore positions');
              if(r.mode!=='finished'){
                const before=JSON.stringify(m.snapshotRunner(r));m.updateRunner(r,100);
                if(m.startJump(r)||before!==JSON.stringify(m.snapshotRunner(r)))throw Error('pause');m.resumeRunner(r);
              }
              const copy=structuredClone(s);m.updateRunner(copy,1/60);m.updateRunner(r,1/60);
              if(JSON.stringify(m.snapshotRunner(copy))!==JSON.stringify(m.snapshotRunner(r)))throw Error('next step');
            }
          }return true;
        }""",dict(plans=INPUTS,upper=UPPER)))

class RunnerVerticalFormalInputTest(unittest.TestCase):
    setUpClass = classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass = classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp = phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown = phase1.RunnerPhase1CompatibilityTest.tearDown

    def test_formal_touch_lower_and_trap_routes_phone_tablet_captures(self):
        import os
        self.context.add_init_script(canvas.MANUAL_FRAMES)
        folder=Path('docs/screenshots/runner-85-vertical')
        for id,inputs,upper in [(id,inputs,False) for id,inputs in INPUTS.items()]+[('S06',UPPER['S06'],True)]:
            for width,height in [(390,844),(1024,768)]:
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
                captures=[(dict(S04=18.1,S05=15.5,S06=17)[id],'high')]
                if id=='S06':captures += [(20.5,'choice'),(22.45 if upper else 22.7,'trap' if upper else 'lower')]
                events=sorted([(t,'jump') for t in inputs]+captures)
                for t,event in events:
                    self.page.evaluate("""async t=>{const c=formalRunner.session;
                      while(c.view.state.elapsed<t-1e-9)await formalRunner.bridge.advance(Math.min(1/60,t-c.view.state.elapsed));
                    }""",t)
                    if event=='jump':
                        frame.locator('#runner-jump').dispatch_event('pointerdown',dict(pointerType='touch',isPrimary=True,button=0))
                        self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
                    else:
                        frame.locator('body').evaluate('()=>runnerClock.step(0)')
                        if event=='high':
                            self.assertTrue(self.page.evaluate("formalRunner.session.view.state.feetY-91>=0"))
                        if os.environ.get('RUNNER_CAPTURE'):
                            folder.mkdir(parents=True,exist_ok=True)
                            device='iphone' if width==390 else 'ipad'
                            self.page.screenshot(path=str(folder/f'{id.lower()}-{device}-{event}.png'))
                        if event=='trap':
                            self.assertEqual(self.page.evaluate('formalRunner.session.view.state.lives'),1)
                            self.assertGreater(self.page.evaluate('formalRunner.session.view.state.invincibleRemaining'),0)
                            # Save/reopen while the trap's one-second shield is active.
                            self.assertTrue(self.page.evaluate("""async()=>{const c=formalRunner.session,m=await loadRunnerModel();
                              await c.pause();const snap=m.snapshotRunner(c.view.state),p=c.view.savedPlay;
                              const reopened=await openRunnerSession('student',p.id,{lifecycle:false});
                              if(JSON.stringify(snap)!==JSON.stringify(m.snapshotRunner(reopened.view.state)))return false;
                              await c.resume();return true;
                            }"""))
                self.page.evaluate("""async()=>{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(1/60);await formalRunner.session.flush();}""")
                frame.locator('body').evaluate('()=>runnerClock.step(0)')
                self.assertEqual(frame.locator('#runner-result-title').inner_text(),'クリア！')
                self.assertEqual(self.page.evaluate('[formalRunner.session.view.savedPlay.score,formalRunner.session.view.savedPlay.result.livesRemaining]'),[100,1 if upper else 2])
                self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).filter(s=>s.id===formalRunner.session.view.savedPlay.id).map(s=>s.amount)"),[30])
