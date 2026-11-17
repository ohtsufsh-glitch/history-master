"""Issue #85 v7: continuous support timers, persistent absence, frozen v1-v6."""
import json
import os
from pathlib import Path
import unittest
import runner_canvas_test as canvas
import runner_phase1_test as phase1
from runner_vertical_test import TRIAL
from runner_balance_cases import INPUTS
BASE=json.loads((Path(__file__).parent/'fixtures/runner85-crumbling-base.json').read_text())
FOLDER=Path('docs/screenshots/runner-85-crumbling')

# Reach a genuine landing using only normal jump inputs. All later inputs are omitted.
LAND="""(id,target,plans)=>{
 const m=runnerModel,s=m.createRunnerState(m.getStage(id,7));s.mode='running';let n=0;
 while(s.mode==='running'&&s.elapsed<40){
  if(n<plans[id].length&&s.elapsed+1e-9>=plans[id][n]){m.startJump(s);n++;}
  m.updateRunner(s,1/120);
  if(s.supportId===target)return s;
 }throw Error('missing natural landing '+id+'/'+target);
}"""
class RunnerCrumblingPhysicsTest(unittest.TestCase):
    setUpClass=classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    model_runner=canvas.RunnerCanvasTest.model_runner
    manual_runner=canvas.RunnerCanvasTest.manual_runner
    open_runner=canvas.RunnerCanvasTest.open_runner
    assert_geometry=canvas.RunnerCanvasTest.assert_geometry
    assert_isolated=canvas.RunnerCanvasTest.assert_isolated
    def model(self):
        p,e,r=self.model_runner();p.evaluate('()=>{window.trial=('+TRIAL+');window.land=('+LAND+');}')
        self.addCleanup(lambda:self.assert_isolated(p,e,r));return p
    def capture(self,name,data):
        if os.environ.get('RUNNER_CAPTURE'):
            FOLDER.mkdir(parents=True,exist_ok=True);(FOLDER/name).write_text(json.dumps(data,indent=2)+'\n')
    def test_published_v1_v6_exact_and_v7_geometry(self):
        p=self.model()
        self.assertEqual(p.evaluate('()=>runnerModel.STAGES.flatMap(s=>Array.from({length:6},(_,i)=>runnerModel.getStage(s.stageId,i+1)).filter(Boolean))'),BASE['stages'])
        rows=p.evaluate("""()=>runnerModel.STAGES.slice(-2).map(s=>({id:s.stageId,v:s.stageVersion,d:s.goalDistance,stars:s.course.filter(o=>o.type==='star').length,crumbling:s.crumbling}))""")
        for r,n,d in zip(rows,[4,7],[7200,8000]):
            self.assertEqual((r['v'],r['d'],r['stars'],len(r['crumbling'])),(7,d,10,n));self.assertTrue(all(x['id']>=0 for x in r['crumbling']))
    def test_clear_30_60_120_and_sequential_three_crumblers(self):
        p=self.model();rows=p.evaluate("""plans=>['S05','S06'].flatMap(id=>[30,60,120].map(hz=>({id,hz,r:trial(runnerModel.getStage(id,7),plans[id],hz)})))""",INPUTS)
        for row in rows:
            r=row['r'];self.assertEqual((r['reason'],r['score'],r['lives']),('clear',100,2),row);self.assertTrue(all(j['ok'] for j in r['jumps']),row)
            if row['id']=='S06':self.assertEqual([l['height'] for l in r['landings'] if 2600<=l['x']<3100],[80,140,185])
        self.capture('physics.json',rows)
    def test_input_windows_at_least_point_two_seconds(self):
        p=self.model();rows=p.evaluate("""plans=>['S05','S06'].flatMap(id=>plans[id].map((t,i)=>{
          const good=v=>{const inputs=plans[id].slice();inputs[i]=v;if(inputs.some((x,j)=>j&&x<=inputs[j-1]))return false;
           const r=trial(runnerModel.getStage(id,7),inputs);return r.reason==='clear'&&r.score===100&&r.lives===2&&r.jumps.every(j=>j.ok);};
          let lo=t,hi=t;for(let n=1;n<=36&&good(t-n/60);n++)lo=t-n/60;for(let n=1;n<=36&&good(t+n/60);n++)hi=t+n/60;
          return {id,t,lo,hi,width:hi-lo};}))""",INPUTS)
        for r in rows:self.assertGreaterEqual(r['width']+1e-8,.2,r)
        self.capture('input-windows.json',rows)
    def test_all_eleven_natural_landings_crack_collapse_pause_restore_and_fall(self):
        p=self.model();rows=p.evaluate("""plans=>{
          const m=runnerModel,rows=[];
          for(const id of ['S05','S06'])for(const c of m.getStage(id,7).crumbling){
            const initial=land(id,c.id,plans),landed=initial.landingUntil-m.CHARACTER_SET.landingSeconds;
            const restore=s=>{const r=m.restoreRunner({stageId:id,stageVersion:7,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});m.resumeRunner(r);return r;};
            for(const hz of [30,60,120]){
              const s=restore(initial),deadline=landed+c.seconds;
              while(s.animationTime<deadline-.001){m.updateRunner(s,Math.min(1/hz,deadline-.001-s.animationTime));}
              const obj=s.objects.find(o=>o.id===c.id);
              if(!obj||s.supportId!==c.id||m.crumbleProgress(s,obj)<.99)throw Error('early collapse or edge '+id+'/'+c.id);
              const paint=()=>{const lines=[],ctx={fillRect(){},strokeRect(){},beginPath(){},moveTo(){},lineTo(x,y){lines.push([x,y])},stroke(){}};m.drawPlatform(ctx,obj,s);return {color:ctx.fillStyle,lines};};
              const before=m.snapshotRunner(s);s.mode='paused';const paused=JSON.stringify(m.snapshotRunner(s));m.updateRunner(s,50);
              if(JSON.stringify(m.snapshotRunner(s))!==paused)throw Error('pause time');s.mode='running';
              const r=restore(s);m.updateRunner(s,.001);m.updateRunner(r,.001);
              if(JSON.stringify(m.snapshotRunner(s))!==JSON.stringify(m.snapshotRunner(r)))throw Error('collapse restore');
              if(s.objects.some(o=>o.id===c.id)||s.supportId===c.id)throw Error('not collapsed '+id+'/'+c.id);
              const fallen=restore(s);m.updateRunner(s,.01);m.updateRunner(fallen,.01);
              if(JSON.stringify(m.snapshotRunner(s))!==JSON.stringify(m.snapshotRunner(fallen))||s.feetY<=initial.feetY||s.velocityY<=0)throw Error('resurrection or no fall '+JSON.stringify({id,c,hz,feetY:s.feetY,supportId:s.supportId}));
              // A jump leaves the object intact and disarms the continuous support timer.
              const jump=restore(initial);if(!m.startJump(jump))throw Error('jump');m.updateRunner(jump,.3);
              if(!jump.objects.some(o=>o.id===c.id)||m.crumbleProgress(jump,jump.objects.find(o=>o.id===c.id))!==0)throw Error('air timer');
              rows.push({id,platform:c.id,hz,landing:landed,seconds:c.seconds,collapse:deadline,paint:paint().lines.length,fallY:s.feetY,snapshotVersion:before.version});
            }
          }return rows;
        }""",INPUTS)
        self.assertEqual(len(rows),33);self.capture('timers.json',rows)
    def test_every_frame_and_post_collapse_snapshot_next_trajectory_strict_validation(self):
        p=self.model();self.assertTrue(p.evaluate("""plans=>{
          const m=runnerModel;
          for(const id of ['S05','S06']){
            const s=m.createRunnerState(m.getStage(id,7));s.mode='running';let n=0;
            while(s.mode==='running'){
              if(n<plans[id].length&&s.elapsed+1e-9>=plans[id][n]){m.startJump(s);n++;}
              const r=m.restoreRunner({stageId:id,stageVersion:7,characterId:'shiba',score:s.score,snapshot:m.snapshotRunner(s)});r.mode=s.mode;
              m.updateRunner(r,1/60);m.updateRunner(s,1/60);
              if(JSON.stringify(m.snapshotRunner(r))!==JSON.stringify(m.snapshotRunner(s)))throw Error('next trajectory');
            }
            const a=land(id,m.getStage(id,7).crumbling[0].id,plans),snap=m.snapshotRunner(a);
            const check=(snapshot,v=7)=>{try{m.restoreRunner({stageId:id,stageVersion:v,characterId:'shiba',score:a.score,snapshot});return false;}catch{return true;}};
            const extra=structuredClone(snap);extra.collapseTimer=1;if(!check(extra))throw Error('extra snapshot field');
            const bad=structuredClone(snap);bad.objects[0].width=999;if(!check(bad))throw Error('object mutation');
            const missing=structuredClone(snap);missing.objects=missing.objects.filter(o=>o.id!==missing.supportId);if(!check(missing))throw Error('missing support');
            const old=m.createRunnerState(m.getStage(id,6));old.mode='running';m.updateRunner(old,13);
            const oldSnap=m.snapshotRunner(old);oldSnap.objects=oldSnap.objects.filter(o=>o.type!=='platform');
            try{m.restoreRunner({stageId:id,stageVersion:6,characterId:'shiba',score:old.score,snapshot:oldSnap});throw Error('old missing allowed');}catch(e){if(e.message==='old missing allowed')throw e;}
          }return true;
        }""",INPUTS))
    def test_omitted_late_jump_collapses_into_fatal_hole_all_hearts(self):
        p=self.model();rows=p.evaluate("""plans=>['S05','S06'].map(id=>{
          const m=runnerModel,c=m.getStage(id,7).crumbling.at(-1),s=land(id,c.id,plans),start=s.elapsed;
          while(s.mode==='running'&&s.elapsed<start+3)m.updateRunner(s,1/120);
          return {id,mode:s.mode,lives:s.lives,reason:s.reason,feetY:s.feetY,x:s.distance,collapsed:!s.objects.some(o=>o.id===c.id)};
        })""",INPUTS)
        for r in rows:self.assertEqual((r['mode'],r['reason'],r['lives'],r['collapsed']),('finished','collision',0,True),r)
        self.capture('failures.json',rows)

class RunnerCrumblingCompatibilityTest(unittest.TestCase):
    setUpClass=classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass=classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp=phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown=phase1.RunnerPhase1CompatibilityTest.tearDown
    def test_frozen_v6_paid_trajectories_and_v6_v7_mixed_backups(self):
        self.assertTrue(self.page.evaluate("""async ({base,plans,landText})=>{
          window.runnerModel=m;window.land=eval('('+landText+')');
          for(const {play,next} of base.states){await installPhase([play]);let c=await openRunnerSession('student',play.id,{lifecycle:false});await c.resume();await c.advance(.1);await c.pause();
            if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(next))throw Error('v6 trajectory');}
          for(const id of ['S05','S06']){
            const old=base.states.find(r=>r.play.stageId===id).play;await installPhase([old]);
            const fresh=await purchaseRunnerPlay({profile:'test',stageId:id,characterId:'shiba'});if(fresh.stageVersion!==7)throw Error('purchase');
            const s=land(id,m.getStage(id,7).crumbling.at(-1).id,plans),crumble=s.crumbling.at(-1);
            for(const t of [.2,crumble.seconds-.2,.02]){
              m.updateRunner(s,t);s.mode='paused';
              const saved=await saveRunnerState('test',fresh.id,(await readAll('runnerPlays')).find(p=>p.id===fresh.id).updatedAt,m.snapshotRunner(s));
              const data=await snapshotAllStores();validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data});await plushInstall(data);
              const c=await openRunnerSession('test',fresh.id,{lifecycle:false});
              if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(m.snapshotRunner(s)))throw Error('paid remaining time/absence');
              const before=JSON.stringify(m.snapshotRunner(c.view.state));await c.advance(100);if(JSON.stringify(m.snapshotRunner(c.view.state))!==before)throw Error('paused paid advance');
              m.resumeRunner(s);
            }
            const c=await openRunnerSession('student',old.id,{lifecycle:false});if(c.view.state.stageVersion!==6)throw Error('old conversion');
            if(DB_VERSION!==10||BACKUP_VERSION!==10||fresh.snapshot.version!==2)throw Error('formats');
          }return true;
        }""",dict(base=BASE,plans=INPUTS,landText=LAND)))

class RunnerCrumblingFormalUITest(unittest.TestCase):
    setUpClass=classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass=classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp=phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown=phase1.RunnerPhase1CompatibilityTest.tearDown
    def test_formal_touch_cracks_hide_pause_collapse_fall_phone_tablet(self):
        import subprocess
        self.context.add_init_script('if(window.parent!==window){'+canvas.MANUAL_FRAMES+'}')
        for id in ['S05','S06']:
            for width,height in [(390,844),(1024,768)]:
                self.page.set_viewport_size(dict(width=width,height=height))
                self.page.evaluate("async()=>{await navigate('home','student');await installPhase();}")
                self.page.locator('#open-runner').click();self.page.locator(f'#formal-stage-cards [data-choice="{id}"]').click()
                f=self.page.frame_locator('iframe');f.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
                f.locator('body').evaluate('()=>runnerClock.step(0)');f.locator('#runner-toggle').click()
                self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
                f.locator('body').evaluate('()=>runnerClock.step(0)')
                cutoff=26.85 if id=='S05' else 29.7
                for t in [t for t in INPUTS[id] if t<=cutoff]:
                    self.page.evaluate("""async t=>{while(formalRunner.session.view.state.elapsed<t-1e-9){if(formalRunner.session.view.state.mode!=='running')throw Error('input route stopped '+t+' '+JSON.stringify(formalRunner.session.view.state));await formalRunner.bridge.advance(Math.min(1/120,t-formalRunner.session.view.state.elapsed));}}""",t)
                    f.locator('#runner-jump').dispatch_event('pointerdown',dict(pointerType='touch',isPrimary=True,button=0))
                    self.assertIsNone(self.page.evaluate('formalRunner.session.view.state.supportId'))
                self.page.evaluate("""async()=>{const c=formalRunner.session;while(c.view.state.supportId!==c.view.state.crumbling.at(-1).id){if(c.view.state.mode!=='running')throw Error('route failed');await formalRunner.bridge.advance(1/120);}await formalRunner.bridge.advance(.1);}""")
                self.page.evaluate("""()=>{const host=document.querySelector('#runner-frame-host'),h=document.querySelector('main > header');scrollTo(0,scrollY+host.getBoundingClientRect().top-h.getBoundingClientRect().height-8);}""")
                f.locator('body').evaluate('()=>runnerClock.step(0)')
                # Hide and restore the real iframe: elapsed time must remain fixed until manual resume.
                f.locator('body').evaluate("""()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));}""")
                self.page.wait_for_function("formalRunner.session.view.state.mode==='paused'")
                before=self.page.evaluate('JSON.stringify(formalRunner.session.view.state)')
                f.locator('body').evaluate("""()=>{runnerClock.step(10000);Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));runnerClock.step(20000);}""")
                self.assertEqual(self.page.evaluate('JSON.stringify(formalRunner.session.view.state)'),before)
                f.locator('#runner-toggle').click();self.page.wait_for_function("formalRunner.session.view.state.mode==='running'")
                f.locator('body').evaluate('()=>runnerClock.step(0)')
                name=f'{id.lower()}-{width}'
                video=Path('/tmp/runner85-captures')/name;video.mkdir(parents=True,exist_ok=True)
                for index in range(34):
                    if index:
                        if self.page.evaluate("formalRunner.session.view.state.mode==='running'"):
                            self.page.evaluate('async()=>await formalRunner.bridge.advance(.05)')
                            f.locator('body').evaluate('()=>runnerClock.step(0)')
                        else:f.locator('body').evaluate('()=>runnerClock.advance(50,120)')
                    s=self.page.evaluate("""()=>{const s=formalRunner.session.view.state;return {mode:s.mode,support:s.supportId,feetY:s.feetY,collapsed:!s.objects.some(o=>o.id===s.crumbling.at(-1).id)};}""")
                    if index==0:self.assertFalse(s['collapsed'])
                    if os.environ.get('RUNNER_CAPTURE'):
                        FOLDER.mkdir(parents=True,exist_ok=True);self.page.screenshot(path=str(video/f'{index:03}.png'))
                        if index in [0,12,15,23,33]:self.page.screenshot(path=str(FOLDER/f'{name}-{[0,12,15,23,33].index(index)}.png'))
                self.assertTrue(s['collapsed']);self.assertEqual(s['mode'],'finished')
                self.assertFalse(f.locator('#runner-result').is_hidden())
                self.assertIn('穴に落ちてしまった',f.locator('#runner-result-message').inner_text())
                self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).filter(s=>s.id===formalRunner.session.view.savedPlay.id).map(s=>s.amount)"),[30])
                if os.environ.get('RUNNER_CAPTURE'):
                    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate','20','-i',str(video/'%03d.png'),'-c:v','libx264','-pix_fmt','yuv420p',str(FOLDER/f'{name}.mp4')],check=True)
    def test_timer_and_collapsed_absence_survive_actual_page_reload(self):
        for index,id in enumerate(['S05','S06']):
            if index:self.tearDown();self.setUp()
            saved=self.page.evaluate("""async ({id,plans,landText})=>{
              await installPhase();window.runnerModel=m;const land=eval('('+landText+')');
              const p=await buy({stageId:id}),s=land(id,m.getStage(id,7).crumbling.at(-1).id,plans);
              m.updateRunner(s,.3);s.mode='paused';await saveRunnerState('student',p.id,p.updatedAt,m.snapshotRunner(s));
              m.resumeRunner(s);m.updateRunner(s,.51);s.mode='paused';return {id:p.id,expected:m.snapshotRunner(s)};
            }""",dict(id=id,plans=INPUTS,landText=LAND))
            self.page.reload();self.page.wait_for_function('appReady')
            actual=self.page.evaluate("""async id=>{const m=await loadRunnerModel(),c=await openRunnerSession('student',id,{lifecycle:false});await c.resume();await c.advance(.51);await c.pause();return m.snapshotRunner(c.view.state);}""",saved['id'])
            self.assertEqual(actual,saved['expected'])
            self.page.reload();self.page.wait_for_function('appReady')
            actual=self.page.evaluate("""async id=>{const m=await loadRunnerModel(),c=await openRunnerSession('student',id,{lifecycle:false});return m.snapshotRunner(c.view.state);}""",saved['id'])
            self.assertEqual(actual,saved['expected'])
