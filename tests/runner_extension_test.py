"""Issue #85 v8 targeted physics, published trajectories, paid saves and UI."""
import json
import os
from pathlib import Path
import unittest
import runner_canvas_test as canvas
import runner_phase1_test as phase1
from runner_extension_cases import INPUTS, V7_INPUTS, HISTORICAL
BASE=json.loads((Path(__file__).parent/'fixtures/runner85-extension-base.json').read_text())
PROBE=(Path(__file__).parent/'runner_extension_probe.js').read_text()
FOLDER=Path('docs/screenshots/runner-85-extension')

def capture(name,data):
    if os.environ.get('RUNNER_CAPTURE'):
        FOLDER.mkdir(parents=True,exist_ok=True)
        (FOLDER/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

class RunnerExtensionPhysicsTest(unittest.TestCase):
    setUpClass=classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    model_runner=canvas.RunnerCanvasTest.model_runner
    manual_runner=canvas.RunnerCanvasTest.manual_runner
    open_runner=canvas.RunnerCanvasTest.open_runner
    assert_geometry=canvas.RunnerCanvasTest.assert_geometry
    assert_isolated=canvas.RunnerCanvasTest.assert_isolated
    def model(self):
        p,e,r=self.model_runner();p.evaluate('()=>{'+PROBE+';window.probe=extensionProbe(runnerModel);}')
        self.addCleanup(lambda:self.assert_isolated(p,e,r));return p
    def test_published_definitions_and_full_v7_frame_hashes(self):
        p=self.model()
        self.assertEqual(p.evaluate('()=>runnerModel.STAGES.flatMap(s=>Array.from({length:7},(_,i)=>runnerModel.getStage(s.stageId,i+1)).filter(Boolean))'),BASE['stages'])
        rows=p.evaluate("""async ({traces,plans})=>{
          const m=runnerModel,rows=[];
          for(const row of traces){const inputs=row.omit?plans[row.id].slice(0,row.id==='S05'?18:21):plans[row.id];
            let frames=0,all='';probe.run(m.getStage(row.id,7),inputs,row.hz,s=>{all+=JSON.stringify(m.snapshotRunner(s))+'\\n';frames++;});
            const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(all));
            rows.push({...row,frames,sha256:[...new Uint8Array(hash)].map(b=>b.toString(16).padStart(2,'0')).join('')});
          }return rows;
        }""",dict(traces=BASE['traces'],plans=V7_INPUTS))
        self.assertEqual(rows,BASE['traces']);capture('v7-traces.json',rows)
    def test_v8_full_clear_all_stars_30_60_120(self):
        p=self.model();rows=p.evaluate("""plans=>['S05','S06'].flatMap(id=>[30,60,120].map(hz=>{
          const stage=runnerModel.getStage(id,8);if(stage.course.filter(e=>e.type==='star').length!==10)throw Error('stars');
          for(const c of stage.crumbling)if(stage.course[c.id].type!=='platform')throw Error('ID');
          return {id,hz,r:probe.run(stage,plans[id],hz)};}))""",INPUTS)
        for row in rows:
            r=row['r'];self.assertEqual((r['reason'],r['score'],r['lives'],r['distance']),('clear',100,2,8000 if row['id']=='S05' else 9000),row)
            self.assertTrue(all(j['ok'] for j in r['jumps']));self.assertEqual(len(r['stars']),10)
            self.assertEqual([l['height'] for l in r['landings'] if l['x']>(7100 if row['id']=='S05' else 7700) and l['support']!='ground'],[120,70] if row['id']=='S05' else [110,170,100])
        capture('physics.json',rows)
    def test_extension_input_windows_all_rates_and_published_exception(self):
        p=self.model();rows=p.evaluate("""plans=>{
          const rows=[];
          for(const id of ['S05','S06'])for(const hz of [30,60,120])for(let i=0;i<plans[id].length;i++){
            const t=plans[id][i],good=v=>{const inputs=plans[id].slice();inputs[i]=v;
              if(inputs.some((v,j)=>j&&v<=inputs[j-1]))return false;
              return probe.fast(runnerModel.getStage(id,8),inputs,hz);};
            let lo=t,hi=t;for(let n=1;n<=Math.ceil(.7*hz)&&good(t-n/hz);n++)lo=t-n/hz;
            for(let n=1;n<=Math.ceil(.7*hz)&&good(t+n/hz);n++)hi=t+n/hz;
            rows.push({id,hz,t,lo,hi,width:hi-lo});
          }return rows;
        }""",INPUTS)
        capture('input-windows.json',rows)
        for row in rows:
            # Preserve published early/middle geometry. Its 30Hz frame quantization is recorded.
            minimum=1/6 if (row['id'],row['hz'],row['t'])==('S05',30,22.65) else .2
            self.assertGreaterEqual(row['width']+1e-8,minimum,row)
    def test_omitted_extension_jumps_fail_and_no_ground_escape(self):
        p=self.model();rows=p.evaluate("""plans=>['S05','S06'].flatMap(id=>{
          const start=id==='S05'?35:38,stage=runnerModel.getStage(id,8);
          return [...plans[id].filter(t=>t>=start),'all-final','no-platforms'].map(skip=>({id,skip,r:probe.run(
            skip==='no-platforms'?{...stage,crumbling:stage.crumbling.slice(0,id==='S05'?4:7),course:stage.course.filter(e=>e.type!=='platform'||e.at*200+822<=(id==='S05'?7200:7750))}:stage,
            skip==='all-final'?plans[id].filter(t=>t<start):plans[id].filter(t=>t!==skip))}));
        })""",INPUTS)
        for row in rows:self.assertLess(row['r']['lives'],2,row)
        capture('failures.json',rows)
    def test_new_hazards_visible_before_contact_and_safe_goal_margin(self):
        p=self.model();self.assertTrue(p.evaluate("""()=>{
          const m=runnerModel;
          for(const id of ['S05','S06']){
            const s=m.getStage(id,8),old=m.getStage(id,7);
            for(const b of s.birds.slice(old.birds.length)){
              // From first visible circular edge to first possible horizontal contact.
              const warning=(960-m.CHARACTER_X-m.COLLISION.characterRadius)/(200+b.speed);
              if(warning<2)throw Error('bird visibility');
              if(s.goalDistance-b.x/1.6<200)throw Error('bird at goal');
            }
            for(const spike of s.spikes.slice(old.spikes.length)){
              if((960-m.CHARACTER_X-m.COLLISION.characterRadius)/200<3)throw Error('spike visibility');
              if(s.goalDistance-spike.x-m.SPIKE_RADIUS<200)throw Error('spike at goal');
              for(let t=0;t<spike.period;t+=.01){
                const state=m.createRunnerState(s);state.elapsed=t;
                const c=m.spikeCenter(state,spike);
                if(c.y-m.SPIKE_RADIUS<0||c.y+m.SPIKE_RADIUS>m.GROUND_Y)throw Error('hidden spike');
              }
            }
            if(s.goalDistance-s.holes.at(-1).end<200)throw Error('hole at goal');
          }return true;
        }"""))
    def test_record_good_and_missing_rejump_paths(self):
        p=self.model();rows=p.evaluate("""plans=>['S05','S06'].flatMap(id=>['good','missing-rejump'].map(route=>{
          const points=[],skip=id==='S05'?37.05:41.4;
          const result=probe.run(runnerModel.getStage(id,8),plans[id].filter(t=>route==='good'||t!==skip),60,s=>{
            if(s.distance>=(id==='S05'?6800:7400))points.push({t:s.elapsed,x:s.distance,height:470-s.feetY,support:s.supportId,lives:s.lives});
          });return {id,route,result,points};}))""",INPUTS)
        capture('route-comparison.json',rows)
        for row in rows:
            if row['route']=='good':self.assertEqual(row['result']['lives'],2)
            else:self.assertLess(row['result']['lives'],2)
    def test_v8_all_crumblers_timers_pause_collapse_and_restore(self):
        p=self.model();rows=p.evaluate("""plans=>{
          const m=runnerModel,rows=[];
          const restore=s=>{const r=m.restoreRunner({stageId:s.stageId,stageVersion:8,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});m.resumeRunner(r);return r;};
          for(const id of ['S05','S06'])for(const c of m.getStage(id,8).crumbling)for(const hz of [30,60,120]){
            const s=probe.land(id,c.id,plans[id]),landed=s.landingUntil-.12,deadline=landed+c.seconds;
            while(s.animationTime<deadline-.001)m.updateRunner(s,Math.min(1/hz,deadline-.001-s.animationTime));
            if(s.supportId!==c.id||!s.objects.some(o=>o.id===c.id))throw Error('early release '+id+'/'+c.id);
            const pos=()=>JSON.stringify([s.birds.map(b=>m.birdCenter(s,b)),s.spikes.map(b=>m.spikeCenter(s,b))]);
            s.mode='paused';const before=JSON.stringify(m.snapshotRunner(s)),phase=pos();m.updateRunner(s,60);
            if(before!==JSON.stringify(m.snapshotRunner(s))||phase!==pos())throw Error('pause');
            m.resumeRunner(s);const r=restore(s);m.updateRunner(s,.001);m.updateRunner(r,.001);
            if(s.objects.some(o=>o.id===c.id)||s.supportId===c.id)throw Error('not collapsed');
            if(JSON.stringify(m.snapshotRunner(s))!==JSON.stringify(m.snapshotRunner(r)))throw Error('timer restore');
            const absent=restore(s);m.updateRunner(absent,1/hz);m.updateRunner(s,1/hz);
            if(JSON.stringify(m.snapshotRunner(s))!==JSON.stringify(m.snapshotRunner(absent)))throw Error('absence restore');
            rows.push({id,platform:c.id,hz,landed,deadline});
          }return rows;
        }""",INPUTS)
        capture('timers.json',rows)
    def test_every_v8_frame_restores_next_motion_and_hazard_phase(self):
        p=self.model();self.assertTrue(p.evaluate("""plans=>{
          const m=runnerModel;for(const id of ['S05','S06'])for(const hz of [30,60,120]){
            probe.run(m.getStage(id,8),plans[id],hz,s=>{
              const r=m.restoreRunner({stageId:id,stageVersion:8,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});r.mode=s.mode;
              const copy=structuredClone(s);m.updateRunner(copy,1/hz);m.updateRunner(r,1/hz);
              if(JSON.stringify(m.snapshotRunner(copy))!==JSON.stringify(m.snapshotRunner(r)))throw Error('trajectory');
              for(const [objects,fn] of [[s.birds,m.birdCenter],[s.spikes,m.spikeCenter]])for(const o of objects){
                if(JSON.stringify(fn(copy,o))!==JSON.stringify(fn(r,o)))throw Error('phase');
              }
            });
          }return true;
        }""",INPUTS))

class RunnerExtensionCompatibilityTest(unittest.TestCase):
    setUpClass=classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass=classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    tearDown=phase1.RunnerPhase1CompatibilityTest.tearDown
    def setUp(self):
        phase1.RunnerPhase1CompatibilityTest.setUp(self)
        self.page.evaluate('()=>{'+PROBE+';window.probe=extensionProbe(m);window.buyHistorical=('+HISTORICAL+');}')
    def test_paid_v7_resume_old_goals_and_v7_v8_mixed_backup(self):
        result=self.page.evaluate("""async plans=>{
          const rows=[];
          for(const id of ['S05','S06']){
            await installPhase();const old=await buyHistorical(id,7,'student');
            const c=await openRunnerSession('student',old.id,{lifecycle:false});await c.resume();await c.advance(.5);await c.pause();
            const before=m.snapshotRunner(c.view.state),count=(await readAll('coinSpends')).length;
            if((await buy({stageId:id})).id!==old.id||(await readAll('coinSpends')).length!==count)throw Error('recharge');
            const again=await openRunnerSession('student',old.id,{lifecycle:false});
            if(JSON.stringify(before)!==JSON.stringify(m.snapshotRunner(again.view.state))||again.view.state.goalDistance!==(id==='S05'?7200:8000))throw Error('v7 changed');
            const fresh=await buy({stageId:id,profile:'test',characterId:'bear'});
            if(fresh.stageVersion!==8||fresh.snapshot.lives!==3)throw Error('latest bear purchase');
            const data=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data});await replaceAllStores(data);
            if(JSON.stringify(data)!==JSON.stringify(await snapshotAllStores()))throw Error('roundtrip');
            for(const p of [old,fresh]){const c=await openRunnerSession(p.profile,p.id,{lifecycle:false});
              rows.push({id,profile:p.profile,version:c.view.state.stageVersion,goal:c.view.state.goalDistance});}
            const end=probe.run(m.getStage(id,7),plans[id]);if(end.reason!=='clear'||end.distance!==(id==='S05'?7200:8000))throw Error('old goal');
          }return rows;
        }""",V7_INPUTS)
        capture('paid-v7-v8.json',result)
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate("async()=>{const c=await openRunnerSession('student',(await readAll('runnerPlays')).find(p=>p.profile==='student'&&p.status==='active').id,{lifecycle:false});return [c.view.state.stageVersion,c.view.state.goalDistance];}"),[7,8000])
    def test_v8_collapsed_snapshot_backup_actual_reload_no_charge(self):
        for id in ['S05','S06']:
            if id=='S06':self.tearDown();self.setUp()
            saved=self.page.evaluate("""async ({id,plans})=>{
              await installPhase();const p=await buy({stageId:id}),stage=m.getStage(id,8),c=stage.crumbling.at(-1);
              const s=probe.land(id,c.id,plans[id]);m.updateRunner(s,.3);s.mode='paused';
              await saveRunnerState('student',p.id,p.updatedAt,m.snapshotRunner(s));
              return {id:p.id,target:c.id,remaining:c.seconds-.3,snapshot:m.snapshotRunner(s),charges:(await readAll('coinSpends')).length};
            }""",dict(id=id,plans=INPUTS))
            self.page.reload();self.page.wait_for_function('appReady')
            collapsed=self.page.evaluate("""async saved=>{
              const m=await loadRunnerModel(),c=await openRunnerSession('student',saved.id,{lifecycle:false});
              if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(saved.snapshot))throw Error('reload timer');
              await c.resume();await c.advance(saved.remaining+.01);await c.pause();
              if(c.view.state.objects.some(o=>o.id===saved.target))throw Error('not disappeared');
              const data=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data});await replaceAllStores(data);
              if((await readAll('coinSpends')).length!==saved.charges)throw Error('charge');
              return m.snapshotRunner(c.view.state);
            }""",saved)
            self.page.reload();self.page.wait_for_function('appReady')
            self.assertEqual(self.page.evaluate("async id=>{const m=await loadRunnerModel(),c=await openRunnerSession('student',id,{lifecycle:false});return m.snapshotRunner(c.view.state);}",saved['id']),collapsed)
    def test_new_official_v8_perfect_results_and_retire_choose_another(self):
        self.assertTrue(self.page.evaluate("""async plans=>{
          for(const profile of ['student','test'])for(const id of ['S05','S06']){
            await installPhase();const p=await buy({profile,stageId:id});
            let c=await openRunnerSession(profile,p.id,{lifecycle:false});await c.resume();let n=0;
            while(c.view.state.mode==='running'){
              if(n<plans[id].length&&c.view.state.elapsed+1e-9>=plans[id][n]){await c.jump();n++;}await c.advance(1/60);
            }await c.flush();if(c.view.savedPlay.result.reason!=='clear'||c.view.savedPlay.score!==100||c.view.savedPlay.result.livesRemaining!==2)throw Error('official clear');
            const d=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:d});
            if(d.coinSpends.find(s=>s.id===p.id).amount!==(profile==='student'?30:0))throw Error('price');
            const retire=await buy({profile,stageId:id,characterId:'bear'});c=await openRunnerSession(profile,retire.id,{lifecycle:false});await c.resume();await c.advance(.5);c.beginRetire();await c.retire();
            const summary=summarizeRunnerPlays(await readAll('runnerPlays'),profile);
            if(summary.bestByStageCharacter[id+':bear'])throw Error('retire best');
            const next=await buy({profile,stageId:'S01',characterId:'bear'});if(next.stageId!=='S01'||next.snapshot.lives!==3)throw Error('choose after retire');
          }return DB_VERSION===10&&BACKUP_VERSION===10;
        }""",INPUTS))

class RunnerExtensionFormalUITest(unittest.TestCase):
    setUpClass=classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass=classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp=phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown=phase1.RunnerPhase1CompatibilityTest.tearDown
    def test_real_touch_extension_and_goal_phone_tablet(self):
        self.context.add_init_script('if(window.parent!==window){'+canvas.MANUAL_FRAMES+'}')
        for id in ['S05','S06']:
            for width,height in [(390,844),(844,390),(1024,768)]:
                self.page.set_viewport_size(dict(width=width,height=height))
                self.page.evaluate("async()=>{await navigate('home','student');await installPhase();}")
                self.page.locator('#open-runner').click()
                self.page.locator(f'#formal-stage-cards [data-choice="{id}"]').click()
                f=self.page.frame_locator('iframe')
                f.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
                f.locator('body').evaluate('()=>runnerClock.step(0)');f.locator('#runner-toggle').click()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
                f.locator('body').evaluate('()=>runnerClock.step(0)')
                events=[(t,'jump') for t in INPUTS[id]]+[(36.65 if id=='S05' else 41.0,'extension'),(39.85 if id=='S05' else 44.85,'goal')]
                for t,kind in sorted(events):
                    self.page.evaluate("""async t=>{while(formalRunner.session.view.state.elapsed<t-1e-9){
                      if(formalRunner.session.view.state.mode!=='running')throw Error('route stopped');
                      await formalRunner.bridge.advance(Math.min(1/120,t-formalRunner.session.view.state.elapsed));}}""",t)
                    if kind=='jump':
                        f.locator('#runner-jump').dispatch_event('pointerdown',dict(pointerType='touch',isPrimary=True,button=0))
                        self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
                    else:
                        f.locator('body').evaluate('()=>runnerClock.step(0)')
                        self.page.evaluate("()=>{const host=document.querySelector('#runner-frame-host'),h=document.querySelector('main > header');scrollTo(0,scrollY+host.getBoundingClientRect().top-h.getBoundingClientRect().height-8);}")
                        if kind=='extension':
                            # Real iframe hide and re-entry freezes game seconds and all phases.
                            f.locator('body').evaluate("()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));}")
                            self.page.wait_for_function("formalRunner.session.view.state.mode==='paused'")
                            before=self.page.evaluate('JSON.stringify(formalRunner.session.view.state)')
                            f.locator('body').evaluate("()=>{runnerClock.step(10000);Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));runnerClock.step(20000);}")
                            self.assertEqual(self.page.evaluate('JSON.stringify(formalRunner.session.view.state)'),before)
                            f.locator('#runner-toggle').click();self.page.wait_for_function("formalRunner.session.view.state.mode==='running'");f.locator('body').evaluate('()=>runnerClock.step(0)')
                        if os.environ.get('RUNNER_CAPTURE'):
                            FOLDER.mkdir(parents=True,exist_ok=True);self.page.screenshot(path=str(FOLDER/f'{id.lower()}-{width}x{height}-{kind}.png'))
                self.page.evaluate("async()=>{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(1/60);}")
                self.assertEqual(self.page.evaluate('[formalRunner.session.view.savedPlay.stageVersion,formalRunner.session.view.savedPlay.score,formalRunner.session.view.savedPlay.result.reason]'),[8,100,'clear'])
                self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).filter(s=>s.id===formalRunner.session.view.savedPlay.id).map(s=>s.amount)"),[30])
