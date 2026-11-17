"""UI-only hole fall; real renderer, frame clock, synthetic paid sessions."""
import json
import os
from pathlib import Path
import unittest
import runner_canvas_test as canvas
import runner_phase1_test as phase1

FOLDER=Path('docs/screenshots/runner-85-balance')
class RunnerFallUITest(unittest.TestCase):
    setUpClass=classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    open_runner=canvas.RunnerCanvasTest.open_runner
    assert_geometry=canvas.RunnerCanvasTest.assert_geometry
    manual_runner=canvas.RunnerCanvasTest.manual_runner
    toggle=canvas.RunnerCanvasTest.toggle
    tap=canvas.RunnerCanvasTest.tap
    def test_fall_freezes_model_until_entire_sprite_exits_then_result(self):
        stage=dict(course=[],goalDistance=2000,holeFailure='fatal',holes=[dict(start=400,end=1000)])
        p,e,r=self.manual_runner(course=stage,probe=True)
        self.toggle(p);p.evaluate('runnerClock.step(0)');self.tap(p)
        p.evaluate('runnerClock.advance(2020,120)')
        frozen=p.evaluate('JSON.stringify(runnerJumpProbe.state)')
        self.assertEqual(p.evaluate('runnerJumpProbe.state.mode'),'finished')
        self.assertTrue(p.locator('#runner-result').is_hidden())
        previous=p.evaluate('runnerClock.snapshot().sprite.y')
        self.assertTrue(p.locator('#runner-toggle').is_disabled())
        samples=[]
        for i in range(80):
            p.locator('#runner-toggle').dispatch_event('click')
            self.tap(p)
            p.evaluate('runnerClock.advance(1000/120,120)')
            row=p.evaluate('''()=>({y:runnerClock.snapshot().sprite.y,result:!document.querySelector('#runner-result').hidden})''')
            self.assertGreaterEqual(row['y'],previous);previous=row['y'];samples.append(row)
            self.assertEqual(p.evaluate('JSON.stringify(runnerJumpProbe.state)'),frozen)
            if row['result']:
                self.assertGreaterEqual(row['y'],540);break
            if row['y']<540:self.assertTrue(p.locator('#runner-result').is_hidden())
        self.assertTrue(samples[-1]['result'])
        self.assertIn('穴に落ちてしまった！もう一度挑戦しよう！',p.locator('#runner-result-message').inner_text())
        self.assertTrue(any(x['y']>=540 and not x['result'] for x in samples))
        self.assertFalse(p.locator('#runner-toggle').is_disabled())
        self.assertEqual(e,[])

class RunnerFallFormalTest(unittest.TestCase):
    setUpClass=classmethod(phase1.RunnerPhase1CompatibilityTest.setUpClass.__func__)
    tearDownClass=classmethod(phase1.RunnerPhase1CompatibilityTest.tearDownClass.__func__)
    setUp=phase1.RunnerPhase1CompatibilityTest.setUp
    tearDown=phase1.RunnerPhase1CompatibilityTest.tearDown
    def start(self,width=390,height=844,stage='S03'):
        self.context.add_init_script('if(window.parent!==window&&!window.runnerClock){'+canvas.MANUAL_FRAMES+'}')
        self.page.set_viewport_size(dict(width=width,height=height))
        self.page.locator('#open-runner').click()
        self.page.locator(f'#formal-stage-cards [data-choice="{stage}"]').click()
        f=self.page.frame_locator('iframe');f.locator('#runner-toggle').filter(has_text='ゲーム開始').wait_for()
        f.locator('body').evaluate('()=>runnerClock.step(0)');f.locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
        f.locator('body').evaluate('()=>runnerClock.step(0)')
        return f
    def finish(self):
        self.page.evaluate('''async()=>{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(1/60);}''')
    def test_paid_fall_saved_immediately_rotation_hide_restore_retry_once(self):
        f=self.start();self.finish()
        frozen=self.page.evaluate('JSON.stringify(formalRunner.session.view.state)')
        f.locator('body').evaluate('()=>runnerClock.step(0)')
        self.assertTrue(f.locator('#runner-result').is_hidden())
        self.assertEqual(self.page.evaluate('formalRunner.session.view.savedPlay.status'),'finished')
        self.assertFalse(self.page.evaluate("formalRunner.select('S05','shiba')"))
        self.assertTrue(self.page.locator('#formal-stage').is_disabled())
        # Hidden time does not teleport the animation. Rotation changes only display size.
        f.locator('body').evaluate('''()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));runnerClock.step(5000);Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));runnerClock.step(10000);}''')
        self.assertTrue(f.locator('#runner-result').is_hidden())
        self.page.set_viewport_size(dict(width=1024,height=768))
        f.locator('body').evaluate('()=>runnerClock.advance(800,120)')
        self.assertFalse(f.locator('#runner-result').is_hidden())
        self.assertEqual(self.page.evaluate('JSON.stringify(formalRunner.session.view.state)'),frozen)
        self.assertIn('穴に落ちてしまった！',f.locator('#runner-result-message').inner_text())
        play_id=self.page.evaluate('formalRunner.session.view.savedPlay.id')
        f.locator('#runner-toggle').dispatch_event('click')
        self.page.wait_for_function("formalRunner.session.view.state.mode==='running'")
        self.assertNotEqual(self.page.evaluate('formalRunner.session.view.savedPlay.id'),play_id)
        self.assertEqual(self.page.evaluate("async id=>(await readAll('coinSpends')).filter(p=>p.id===id).map(p=>p.amount)",play_id),[30])
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).filter(p=>p.id===formalRunner.session.view.savedPlay.id).map(p=>p.amount)"),[30])

        # Finished result survives reload without repeating a fall or repurchasing.
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate("async id=>(await readAll('coinSpends')).filter(p=>p.id===id).length",play_id),1)
        self.assertEqual(self.page.evaluate("async id=>(await readAll('runnerPlays')).filter(p=>p.status==='finished'&&p.id===id).length",play_id),1)

    def test_slow_and_failed_save_do_not_reveal_result_early(self):
        for failed in [False,True]:
            if failed:
                self.tearDown();self.setUp()
            f=self.start()
            self.page.evaluate('''fail=>{
              const save=saveRunnerState;window.releaseSave=null;
              saveRunnerState=async(...args)=>{if(args[3].mode==='finished'){await new Promise(r=>releaseSave=r);if(fail)throw Error('test save failure');}return save(...args);};
              window.finishPromise=(async()=>{while(formalRunner.session.view.state.mode==='running')await formalRunner.bridge.advance(1/60);})().catch(()=>{});
            }''',failed)
            self.page.wait_for_function('releaseSave!==null')
            f.locator('body').evaluate('()=>runnerClock.step(0)')
            self.assertTrue(f.locator('#runner-result').is_hidden())
            f.locator('body').evaluate('()=>runnerClock.advance(200,120)')
            self.assertTrue(f.locator('#runner-result').is_hidden())
            self.page.evaluate('releaseSave()')
            self.page.evaluate('finishPromise')
            self.assertTrue(f.locator('#runner-result').is_hidden())
            f.locator('body').evaluate('()=>runnerClock.advance(700,120)')
            self.assertFalse(f.locator('#runner-result').is_hidden())
            self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).filter(p=>p.id===formalRunner.session.view.savedPlay.id).length"),1)
            if failed:self.assertIn('まだ保存できていません',f.locator('#runner-result-title').inner_text())

    def test_collision_result_is_immediate(self):
        f=self.start(stage='S01');self.finish();f.locator('body').evaluate('()=>runnerClock.step(0)')
        self.assertFalse(f.locator('#runner-result').is_hidden())
        self.assertNotIn('穴',f.locator('#runner-result-message').inner_text())

    def test_fall_phone_tablet_frames_and_optional_video(self):
        import subprocess
        for width,height in [(390,844),(1024,768)]:
            if width==1024:self.tearDown();self.setUp()
            f=self.start(width,height)
            self.page.evaluate("""()=>{const h=document.querySelector('main > header'),host=document.querySelector('#runner-frame-host');scrollTo(0,scrollY+host.getBoundingClientRect().top-h.getBoundingClientRect().height-8);}""")
            self.finish();f.locator('body').evaluate('()=>runnerClock.step(0)')
            captured=set();rows=[];video=Path('/tmp/runner85-fall-video');video.mkdir(exist_ok=True)
            for i in range(150):
                f.locator('body').evaluate('()=>runnerClock.advance(1000/120,120)')
                row=f.locator('body').evaluate("""()=>({y:runnerClock.snapshot().sprite?.y,result:!document.querySelector('#runner-result').hidden})""")
                rows.append(row)
                key='result' if row['result'] else 'gone' if row['y']>=540 else 'falling' if row['y']>=450 else None
                if key and key not in captured:
                    captured.add(key)
                    if os.environ.get('RUNNER_CAPTURE'):
                        FOLDER.mkdir(parents=True,exist_ok=True)
                        self.page.screenshot(path=str(FOLDER/f'fall-{width}-{key}.png'))
                if width==390 and os.environ.get('RUNNER_CAPTURE') and i%6==0:
                    self.page.screenshot(path=str(video/f'{i//6:03}.png'))
            self.assertEqual(captured,{'falling','gone','result'})
            if os.environ.get('RUNNER_CAPTURE'):
                (FOLDER/f'fall-{width}-frames.json').write_text(json.dumps(rows,indent=2)+'\n')
                if width==390:
                    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate','20','-i',str(video/'%03d.png'),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-pix_fmt','yuv420p',str(FOLDER/'fall.mp4')],check=True)
