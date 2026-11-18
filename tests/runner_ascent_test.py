"""Issue #85 v5: mandatory pit ascent, final platforms, paid compatibility."""
import json
from pathlib import Path
import unittest
import runner_canvas_test as canvas
import runner_phase1_test as phase1
from runner_vertical_test import TRIAL
from runner_ascent_cases import INPUTS, UPPER
BASE=json.loads((Path(__file__).parent/'fixtures/runner85-ascent-base.json').read_text())

class RunnerAscentPhysicsTest(unittest.TestCase):
    setUpClass=classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    manual_runner=canvas.RunnerCanvasTest.manual_runner
    open_runner=canvas.RunnerCanvasTest.open_runner
    model_runner=canvas.RunnerCanvasTest.model_runner
    assert_isolated=canvas.RunnerCanvasTest.assert_isolated
    assert_geometry=canvas.RunnerCanvasTest.assert_geometry

    def model(self):
        p,e,r=self.model_runner()
        p.evaluate('()=>{window.trial=('+TRIAL+');}')
        self.addCleanup(lambda:self.assert_isolated(p,e,r))
        return p

    def test_frozen_definitions_counts_and_unchanged_branches(self):
        p=self.model()
        self.assertEqual(p.evaluate('()=>runnerModel.STAGES.map(s=>runnerModel.getStage(s.stageId,["S05","S06"].includes(s.stageId)?4:s.stageVersion))'),BASE['stages'])
        self.assertTrue(p.evaluate('''()=>{
          const m=runnerModel;
          for(const id of ['S05','S06']){
            const s=m.getStage(id,5),old=m.getStage(id,4),branch=e=>{const x=e.at*200+822;return x>= (id==='S05'?3800:4100)&&x< (id==='S05'?4800:5400)};
            if(JSON.stringify(s.course.filter(branch))!==JSON.stringify(old.course.filter(branch)))throw Error('branch');
            if(s.goalDistance!==(id==='S05'?7200:8000)||s.course.filter(e=>e.type==='star').length!==10||s.holeFailure!=='fatal')throw Error('invariants');
            if(!s.birds.every(b=>b.speed===120)||s.spikes.length-old.spikes.length!==(id==='S05'?2:5))throw Error('hazards');
          }
          const s=m.getStage('S06',5),decks=s.course.filter(e=>e.type==='platform'&&e.at*200+822>=5400);
          return s.birds.length>=20&&decks.length===7&&decks.every(e=>e.width>=100&&e.width<=220)&&s.holes[0].end<4100;
        }'''))

    def test_representative_clear_landings_and_upper_trap_30_60_120(self):
        p=self.model()
        rows=p.evaluate('''plans=>Object.entries(plans).filter(([id])=>id!=='S04').flatMap(([id,inputs])=>[30,60,120].map(hz=>({id,hz,r:trial(runnerModel.getStage(id,5),inputs,hz)})))''',INPUTS)
        for row in rows:
            r=row['r'];self.assertEqual((r['reason'],r['score'],r['lives']),('clear',100,2),row)
            self.assertTrue(all(j['ok'] for j in r['jumps']),row);self.assertGreaterEqual(r['minY'],0,row)
            hs=[l['height'] for l in r['landings']]
            for h in ([80,150,200,140,70] if row['id']=='S05' else [80,140,185,210,100,150,70,130]):self.assertIn(h,hs,row)
            if row['id']=='S06':self.assertEqual(len([l for l in r['landings'] if l['x']>5400]),7,row)
        for hz in [30,60,120]:
            r=p.evaluate('''({inputs,hz})=>trial(runnerModel.getStage('S06',5),inputs,hz)''',dict(inputs=UPPER['S06'],hz=hz))
            self.assertEqual((r['reason'],r['score'],r['lives']),('clear',100,1),r)
            self.assertTrue(any(h['birds'] for h in r['hits']),r)

    def test_unattended_ascent_and_missed_rejumps_are_fatal(self):
        p=self.model()
        for id in ['S05','S06']:
            limit=11 if id=='S05' else 12
            r=p.evaluate('''({id,inputs})=>trial(runnerModel.getStage(id,5),inputs)''',dict(id=id,inputs=[t for t in INPUTS[id] if t<limit]))
            self.assertEqual((r['reason'],r['lives']),('collision',0),r)
            # Remove individual ascent/final jumps from the real complete plan.
            for t in ([12.65,13.75] if id=='S05' else [13.35,14.3,15.2,28,29.7,31.4,33.1,34.8,36.5,38.2]):
                r=p.evaluate('''({id,inputs})=>trial(runnerModel.getStage(id,5),inputs)''',dict(id=id,inputs=[v for v in INPUTS[id] if v!=t]))
                self.assertEqual((r['reason'],r['lives']),('collision',0),(id,t,r))

    def test_one_ground_jump_cannot_span_pits_even_with_shield_and_hearts(self):
        p=self.model()
        self.assertTrue(p.evaluate('''()=>{
          const m=runnerModel;
          // Isolate ground reach from enemies and decks; use the production jump/fall physics.
          for(const id of ['S05','S06'])for(const shield of [0,100])for(const lives of [1,3]){
            const original=m.getStage(id,5),hole=original.holes[0];
            for(let offset=0;offset<=200;offset+=5){
              const s=m.createRunnerState({...original,course:[],birds:[],spikes:[]});
              s.distance=hole.start-offset;s.elapsed=s.distance/s.speed;s.mode='running';s.lives=lives;s.invincibleRemaining=shield;
              m.startJump(s);while(s.mode==='running'&&s.distance<hole.end)m.updateRunner(s,1/60);
              if(s.mode!=='finished'||s.lives!==0||s.feetY<=470||s.distance>=hole.end)throw Error('ground escape');
            }
          }return true;
        }'''))

    def test_added_bird_spike_positions_collision_and_canvas(self):
        p=self.model()
        self.assertTrue(p.evaluate('''()=>{
          const m=runnerModel;
          for(const id of ['S05','S06']){
            const s=m.createRunnerState(m.getStage(id,5));s.mode='running';
            for(const spike of s.spikes){
              s.elapsed=0;s.distance=spike.x;const initial=m.spikeCenter(s,spike);s.elapsed=spike.period;
              if(Math.hypot(initial.x-m.spikeCenter(s,spike).x,initial.y-m.spikeCenter(s,spike).y)>1e-8)throw Error('period');
              s.elapsed=1.27;const center=m.spikeCenter(s,spike);s.supportId=null;s.feetY=center.y+43;
              if(!m.touchesSpike(s,spike))throw Error('spike hit');
              s.feetY=center.y+43+54.001;if(m.touchesSpike(s,spike))throw Error('spike miss');
              s.feetY=center.y+43+53.999;if(!m.touchesSpike(s,spike))throw Error('spike boundary');
              const points=[],ctx={save(){},restore(){},beginPath(){},closePath(){},fill(){},stroke(){},arc(){},moveTo(x,y){points.push({x,y})},lineTo(x,y){points.push({x,y})}};
              m.drawSpike(ctx,s,spike);
              if(points.length!==24||points.some(p=>Math.hypot(p.x-center.x,p.y-center.y)>26.001))throw Error('paint');
            }
            for(const bird of s.birds){
              s.elapsed=1;s.distance=bird.x-120;s.supportId=null;s.feetY=470-bird.height+43;
              if(!m.touchesBird(s,bird))throw Error('bird hit');s.feetY+=56.001;
              if(m.touchesBird(s,bird))throw Error('bird miss');
              const a=m.birdCenter(s,bird);s.elapsed+=.25;const b=m.birdCenter(s,bird);
              if(Math.abs(a.x-b.x-30)>1e-7)throw Error('bird speed');
              if(b.y-28<0)throw Error('bird clipped');
            }
          }return true;
        }'''))

    def test_major_input_windows_and_motion_restore(self):
        p=self.model()
        rows=p.evaluate('''plans=>Object.entries(plans).filter(([id])=>id!=='S04').flatMap(([id,inputs])=>inputs.map((t,i)=>{
          const stage=runnerModel.getStage(id,5);const good=v=>{const plan=inputs.slice();plan[i]=v;
            if(plan.some((x,j)=>j&&x<=plan[j-1]))return false;
            const r=trial(stage,plan);return r.reason==='clear'&&r.score===100&&r.lives===2&&r.jumps.every(j=>j.ok)&&r.landings.some(l=>l.height===(id==='S05'?200:210));};
          let lo=t,hi=t;for(let n=1;n<=36&&good(t-n/60);n++)lo=t-n/60;for(let n=1;n<=36&&good(t+n/60);n++)hi=t+n/60;
          return {id,t,lo,hi,width:hi-lo};
        }))''',INPUTS)
        for row in rows:self.assertGreaterEqual(row['width']+1e-8,.2,row)
        print('v5 minimum input windows:',{id:round(min(r['width'] for r in rows if r['id']==id),3) for id in ['S05','S06']})
        self.assertTrue(p.evaluate('''plans=>{
          const m=runnerModel;
          for(const id of ['S05','S06']){
            const s=m.createRunnerState(m.getStage(id,5));s.mode='running';let n=0;
            while(s.mode==='running'){
              if(n<plans[id].length&&s.elapsed+1e-9>=plans[id][n]){m.startJump(s);n++;}
              const snap=m.snapshotRunner(s),r=m.restoreRunner({stageId:id,stageVersion:5,characterId:'shiba',score:s.score,snapshot:snap});
              if(JSON.stringify(snap)!==JSON.stringify({...m.snapshotRunner(r),mode:s.mode}))throw Error('round trip');
              r.mode=s.mode;m.updateRunner(r,1/60);m.updateRunner(s,1/60);
              if(JSON.stringify(m.snapshotRunner(r))!==JSON.stringify(m.snapshotRunner(s)))throw Error('next trajectory');
              if(JSON.stringify(r.spikes.map(b=>m.spikeCenter(r,b)))!==JSON.stringify(s.spikes.map(b=>m.spikeCenter(s,b))))throw Error('spikes');
            }
          }return true;
        }''',INPUTS))

class RunnerAscentCompatibilityTest(unittest.TestCase):
    setUpClass=classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass=classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp=phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown=phase1.RunnerPhase1CompatibilityTest.tearDown

    def test_v4_states_and_mixed_v4_v5_backup(self):
        self.assertTrue(self.page.evaluate('''async base=>{
          for(const {play,next} of base.states){
            await installPhase([play]);const c=await openRunnerSession('student',play.id,{lifecycle:false});
            await c.resume();await c.advance(.1);await c.pause();
            if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(next))throw Error('v4 trajectory');
            const again=await openRunnerSession('student',play.id,{lifecycle:false});
            if(JSON.stringify(m.snapshotRunner(again.view.state))!==JSON.stringify(next))throw Error('v4 save');
          }
          const old=base.states.find(r=>r.play.stageId==='S06'&&r.play.snapshot.elapsed>28).play;
          await installPhase([old]);const fresh=await purchaseRunnerPlay({profile:'test',stageId:'S06',characterId:'shiba'});
          if(fresh.stageVersion!==7)throw Error('new version');
          const data=await snapshotAllStores(),backup=JSON.parse(JSON.stringify({backupFormat:BACKUP_FORMAT,backupVersion:10,data}));
          validateBackup(backup);await plushInstall(backup.data);
          if(JSON.stringify(data)!==JSON.stringify(await snapshotAllStores()))throw Error('backup stores');
          for(const p of [old,fresh]){
            const c=await openRunnerSession(p.profile,p.id,{lifecycle:false});
            if(c.view.state.stageVersion!==p.stageVersion)throw Error('wrong resume');
          }return true;
        }''',BASE))
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate('''async()=>{const p=(await readAll('runnerPlays')).find(p=>p.profile==='student'&&p.status==='active');return (await openRunnerSession(p.profile,p.id,{lifecycle:false})).view.state.stageVersion;}'''),4)
