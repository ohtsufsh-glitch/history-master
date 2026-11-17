"""Issue #85 v6 targeted course and frozen v1-v5 / paid-play compatibility."""
import json
from pathlib import Path
import unittest
import runner_canvas_test as canvas
import runner_phase1_test as phase1
from runner_vertical_test import TRIAL
from runner_balance_cases import INPUTS
BASE=json.loads((Path(__file__).parent/'fixtures/runner85-balance-base.json').read_text())

class RunnerBalancePhysicsTest(unittest.TestCase):
    setUpClass=classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    model_runner=canvas.RunnerCanvasTest.model_runner
    manual_runner=canvas.RunnerCanvasTest.manual_runner
    open_runner=canvas.RunnerCanvasTest.open_runner
    assert_geometry=canvas.RunnerCanvasTest.assert_geometry
    assert_isolated=canvas.RunnerCanvasTest.assert_isolated
    def model(self):
        p,e,r=self.model_runner();p.evaluate('()=>window.trial=('+TRIAL+')')
        self.addCleanup(lambda:self.assert_isolated(p,e,r));return p

    def test_all_published_definitions_frozen_and_v6_geometry(self):
        p=self.model()
        self.assertEqual(p.evaluate('()=>runnerModel.STAGES.flatMap(s=>Array.from({length:5},(_,i)=>runnerModel.getStage(s.stageId,i+1)).filter(Boolean))'),BASE['stages'])
        self.assertTrue(p.evaluate('''()=>{
          const m=runnerModel,a=m.getStage('S05',6),b=m.getStage('S06',6),old=m.getStage('S06',5);
          const late=s=>s.course.filter(e=>e.at*200+822>=5400);
          if(JSON.stringify(late(b))!==JSON.stringify(late(old))||JSON.stringify(b.holes)!==JSON.stringify(old.holes)||JSON.stringify(b.birds.slice(7))!==JSON.stringify(old.birds.slice(7)))throw Error('S06 final altered');
          const decks=a.course.filter(e=>e.type==='platform'&&e.at*200+822>=4800);
          return a.holes.filter(h=>h.start>=3900&&h.end<4800).length===3&&decks.length===7&&decks.every(e=>e.width===220)&&a.birds.length===12&&a.spikes.length===6&&b.birds.length===21&&b.spikes.length===16;
        }'''))

    def test_shiba_30_60_120_upper_clear_all_stars_sequential_landings(self):
        p=self.model()
        rows=p.evaluate('''plans=>['S05','S06'].flatMap(id=>[30,60,120].map(hz=>({id,hz,r:trial(runnerModel.getStage(id,6),plans[id],hz)})))''',INPUTS)
        for row in rows:
            r=row['r'];self.assertEqual((r['reason'],r['score'],r['lives']),('clear',100,2),row)
            self.assertTrue(all(j['ok'] for j in r['jumps']),row);self.assertGreaterEqual(r['minY'],0,row)
            late=[l for l in r['landings'] if l['x']>=(4800 if row['id']=='S05' else 5390)]
            self.assertEqual(len(late),7,row)
            self.assertEqual([l['height'] for l in late],[100,150,70,140,80,130,70],row)

    def test_missed_jumps_and_lower_route_fail(self):
        p=self.model()
        rows=p.evaluate('''plans=>{
          const rows=[];for(const id of ['S05','S06']){
            const stage=runnerModel.getStage(id,6),inputs=plans[id];
            const skip=id==='S05'?[19.05,20.1,21.45,22.65,23.95,25.15,26.85,28.55,30.25,31.95,33.65]:[22.35,23.45,24.55,25.65];
            for(const t of skip)rows.push({id,skip:t,r:trial(stage,inputs.filter(x=>x!==t))});
            rows.push({id,skip:'lower',r:trial(stage,inputs.filter(t=>t<19))});
            if(id==='S05')rows.push({id,skip:'single-entry-jump',r:trial(stage,[...inputs.filter(t=>t<19),19.05])});
          }return rows;
        }''',INPUTS)
        for row in rows:
            r=row['r']
            if row['id']=='S05' and row['skip'] not in [21.45,22.65]:self.assertEqual((r['reason'],r['lives']),('collision',0),row)
            else:self.assertLess(r['lives'],2,row)
        print('v6 missed input / lower failures:',[(r['id'],r['skip'],r['r']['hits'][0]) for r in rows])

    def test_measured_input_windows(self):
        p=self.model()
        rows=p.evaluate('''plans=>['S05','S06'].flatMap(id=>plans[id].map((t,i)=>{
          const good=v=>{const inputs=plans[id].slice();inputs[i]=v;
            if(inputs.some((x,j)=>j&&x<=inputs[j-1]))return false;
            const r=trial(runnerModel.getStage(id,6),inputs);return r.reason==='clear'&&r.score===100&&r.lives===2&&r.jumps.every(j=>j.ok);};
          let lo=t,hi=t;for(let n=1;n<=36&&good(t-n/60);n++)lo=t-n/60;for(let n=1;n<=36&&good(t+n/60);n++)hi=t+n/60;
          return {id,t,lo,hi,width:hi-lo};
        }))''',INPUTS)
        for row in rows:
            self.assertGreaterEqual(row['width']+1e-8,.2,row)
            if row['id']=='S06' and row['t'] in [22.35,23.45,24.55,25.65]:self.assertLessEqual(row['width'],.301,row)
        print('v6 input windows:',rows)
        if __import__('os').environ.get('RUNNER_CAPTURE'):
            folder=Path('docs/screenshots/runner-85-balance');folder.mkdir(parents=True,exist_ok=True)
            (folder/'input-windows.json').write_text(json.dumps(rows,indent=2)+'\n')

    def test_spikes_period_collision_paint_and_upper_clearance(self):
        p=self.model()
        self.assertTrue(p.evaluate('''()=>{
          const m=runnerModel,s=m.createRunnerState(m.getStage('S06',6));
          for(const spike of s.spikes.slice(-5)){
            s.distance=spike.x;
            const top=470-spike.height-spike.amplitude-26;
            if(top<=352||spike.x+26>=5140||spike.x-26<=4360)throw Error('deck penetration');
            s.elapsed=0;const a=m.spikeCenter(s,spike);s.elapsed=spike.period;const b=m.spikeCenter(s,spike);
            if(Math.hypot(a.x-b.x,a.y-b.y)>1e-8)throw Error('period');
            const points=[],ctx={save(){},restore(){},beginPath(){},closePath(){},fill(){},stroke(){},arc(){},moveTo(x,y){points.push({x,y})},lineTo(x,y){points.push({x,y})}};
            m.drawSpike(ctx,s,spike);if(points.length!==24||points.some(p=>Math.hypot(p.x-b.x,p.y-b.y)>26.001))throw Error('paint');
            for(let t=0;t<spike.period;t+=.01){s.elapsed=t;s.distance=spike.x;s.feetY=320;if(m.touchesSpike(s,spike))throw Error('upper hit');}
            s.feetY=m.spikeCenter(s,spike).y+43;if(!m.touchesSpike(s,spike))throw Error('lower collision');
          }
          for(const b of s.birds.slice(3,7)){s.elapsed=1;const x=m.birdCenter(s,b).x;s.elapsed=2;if(Math.abs(x-m.birdCenter(s,b).x-120)>1e-8)throw Error('speed');}
          return true;
        }'''))

    def test_v6_every_frame_snapshot_restore_next_trajectory(self):
        p=self.model()
        self.assertTrue(p.evaluate('''plans=>{
          const m=runnerModel;for(const id of ['S05','S06']){
            const s=m.createRunnerState(m.getStage(id,6));s.mode='running';let n=0;
            while(s.mode==='running'){
              if(n<plans[id].length&&s.elapsed+1e-9>=plans[id][n]){m.startJump(s);n++;}
              const r=m.restoreRunner({stageId:id,stageVersion:6,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});r.mode=s.mode;
              m.updateRunner(r,1/60);m.updateRunner(s,1/60);
              if(JSON.stringify(m.snapshotRunner(r))!==JSON.stringify(m.snapshotRunner(s)))throw Error('next trajectory');
            }
          }return true;
        }''',INPUTS))

class RunnerBalanceCompatibilityTest(unittest.TestCase):
    setUpClass=classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass=classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp=phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown=phase1.RunnerPhase1CompatibilityTest.tearDown
    def test_v5_exact_resume_and_v5_v6_mixed_backup(self):
        self.assertTrue(self.page.evaluate('''async base=>{
          for(const {play,next} of base.states){
            await installPhase([play]);const c=await openRunnerSession('student',play.id,{lifecycle:false});await c.resume();await c.advance(.1);await c.pause();
            if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(next))throw Error('v5 trajectory');
            const again=await openRunnerSession('student',play.id,{lifecycle:false});if(JSON.stringify(m.snapshotRunner(again.view.state))!==JSON.stringify(next))throw Error('v5 resume');
          }
          for(const id of ['S05','S06']){
            const old=base.states.find(r=>r.play.stageId===id&&r.play.snapshot.elapsed>22).play;
            await installPhase([old]);const fresh=await purchaseRunnerPlay({profile:'test',stageId:id,characterId:'shiba'});if(fresh.stageVersion!==6)throw Error('purchase version');
            const data=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data});await plushInstall(data);
            if(JSON.stringify(data)!==JSON.stringify(await snapshotAllStores()))throw Error('backup stores');
            for(const p of [old,fresh]){const c=await openRunnerSession(p.profile,p.id,{lifecycle:false});if(c.view.state.stageVersion!==p.stageVersion)throw Error('version conversion');}
          }return true;
        }''',BASE))
