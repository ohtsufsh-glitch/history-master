"""Issue #127: bear physics, supplied art, paid saves and compatibility. Synthetic DB only."""
import hashlib
import unittest

import runner_canvas_test as canvas
import runner_session_test as sessions
import runner_integration_test as integration


FEET = dict(zip(canvas.SHIBA_FRAMES, [449,449,449,449,449,420,404,422,449]))


class RunnerBearModelTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    model_runner = canvas.RunnerCanvasTest.model_runner
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    open_runner = canvas.RunnerCanvasTest.open_runner
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry

    def test_physics_and_three_hearts_at_30_60_120_hz(self):
        page, errors, _ = self.model_runner()
        rows = page.evaluate('''()=>{
          const m=runnerModel,c=m.getCharacter('bear'),rows=[];
          if(m.CHARACTERS.length!==5||c.name!=='くま'||c.ability.speed!=='低'||c.ability.jump!=='中'||
            c.feature!=='ゆっくり走る・ハート3つ'||c.airJumps!==0)throw Error('catalog');
          for(const hz of [30,60,120]) {
            const s=m.createRunnerState([],'bear');s.mode='running';m.startJump(s);
            const unchanged=JSON.stringify(s);if(m.startJump(s)||unchanged!==JSON.stringify(s))throw Error('air jump');
            let apex=0;
            for(let f=0;f<hz;f++){m.updateRunner(s,1/hz);apex=Math.max(apex,470-s.feetY);}
            const jumpDistance=s.distance;
            const lives=[s.lives];
            for(let hit=0;hit<3;hit++) {
              s.objects=[{id:hit,type:'obstacle',x:186}];m.updateRunner(s,0);lives.push(s.lives);
              if(hit<2){s.objects=[];for(let f=0;f<=hz;f++)m.updateRunner(s,1/hz);}
            }
            rows.push({hz,speed:s.speed,height:s.jump.height,duration:s.jump.duration,apex,
              jumpDistance,lives,mode:s.mode,reason:s.reason,feet:s.feetY});
          }return rows;
        }''')
        for r in rows:
            self.assertEqual([r[k] for k in ('speed','height','duration')], [180,130,1])
            self.assertAlmostEqual(r['apex'],130,places=6)
            self.assertAlmostEqual(r['jumpDistance'],180,places=6)
            self.assertEqual(r['lives'],[3,2,1,0])
            self.assertEqual([r[k] for k in ('mode','reason','feet')],['finished','collision',470])
        self.assertEqual(errors,[])

    def test_supplied_silhouettes_match_each_pose_foot_anchor(self):
        paths=list((canvas.ROOT/'runner/assets/bear').glob('*.webp'))
        self.assertEqual(len(paths),9)
        self.assertEqual(len({hashlib.sha256(p.read_bytes()).digest() for p in paths}),9)
        page, errors, _ = self.model_runner()
        rows=page.evaluate('''async()=>{
          const rows=[];
          for(const [pose,frame] of Object.entries(runnerModel.ANIMATION_SETS.bear.frames)) {
            const im=new Image();im.src=frame.src;await im.decode();
            const c=document.createElement('canvas');c.width=c.height=512;
            const ctx=c.getContext('2d');ctx.drawImage(im,0,0);
            const data=ctx.getImageData(0,0,512,512).data;
            let bottom=0,transparent=0,solid=0;
            for(let i=3;i<data.length;i+=4){if(data[i])bottom=Math.floor(i/4/512)+1;else transparent++;if(data[i]===255)solid++;}
            rows.push({pose,size:[im.naturalWidth,im.naturalHeight],bottom,
              feet:frame.feetRatio*512,transparent,solid});
          }return rows;
        }''')
        for r in rows:
            self.assertEqual(r['size'],[512,512])
            self.assertEqual(r['bottom'],FEET[r['pose']])
            self.assertEqual(r['feet'],r['bottom'])
            self.assertGreater(r['transparent'],150000)
            self.assertGreater(r['solid'],20000)
        self.assertEqual(errors,[])


class RunnerBearSaveTest(unittest.TestCase):
    setUpClass = classmethod(sessions.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(sessions.RunnerSessionTest.tearDownClass.__func__)
    setUp = sessions.RunnerSessionTest.setUp
    tearDown = sessions.RunnerSessionTest.tearDown

    def test_purchase_resume_clear_gameover_retire_and_profile_scores(self):
        result=self.page.evaluate('''async()=>{
          const rows=[];
          for(const profile of ['student','test']) {
            await install(120);
            for(const outcome of ['clear','gameover','retire']) {
              const p=await buy({profile,characterId:'bear'});
              let c=await openRunnerSession(profile,p.id,{lifecycle:false});await c.resume();
              await c.jump();await c.advance(.2);await c.pause();
              const checkpoint=m.snapshotRunner(c.view.state);await c.close();
              c=await openRunnerSession(profile,p.id,{lifecycle:false});
              if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(checkpoint))throw Error('resume');
              await c.resume();
              if(outcome==='retire'){c.beginRetire();await c.retire();}
              else for(let f=0;f<1200&&c.view.state.mode==='running';f++) {
                const s=c.view.state;
                if(outcome==='clear'&&s.supportId==='ground'&&s.objects.some(o=>o.type==='obstacle'&&o.x-186>90&&o.x-186<110))await c.jump();
                await c.advance(1/30);
              }
              const saved=c.view.savedPlay;
              if(saved.status!=='finished'||saved.result.reason!==outcome)throw Error('finish '+outcome+' '+JSON.stringify(saved));
              rows.push([profile,outcome,saved.result.livesRemaining]);await c.close();
            }
            const data=await snapshotAllStores(),sum=summarizeRunnerPlays(data.runnerPlays,profile);
            validateRunnerPlays(data.runnerPlays);
            if(data.coinSpends.length!==3||data.coinSpends.some(s=>s.amount!==(profile==='student'?30:0)))throw Error('charge');
            if(sum.bestByStageCharacter['S01:bear'].result.reason==='retire'||!sum.unlockedStageIds.includes('S02'))throw Error('summary');
            if(Object.keys(summarizeRunnerPlays(data.runnerPlays,profile==='student'?'test':'student').bestByStage).length)throw Error('profile');
            if(Object.keys(summarizeRunnerPlays(data.runnerPlays.filter(p=>p.result.reason==='retire'),profile).bestByStage).length)throw Error('retire best');
          }return rows;
        }''')
        self.assertEqual(len(result),6)

    def test_mixed_backup_old_backups_and_s05_s06_latest_resume(self):
        self.assertTrue(self.page.evaluate('''async()=>{
          await plushInstall(plushFixture([], 'test'));
          for(const characterId of ['shiba','sloth','goldfish','salamander','bear']) {
            const p=await buy({characterId}),c=await openRunnerSession('student',p.id,{lifecycle:false});
            await c.resume();const maxFrames=Math.ceil(c.view.state.goalDistance/c.view.state.speed/.05)+1;
            for(let f=0;f<maxFrames&&c.view.state.mode==='running';f++)await c.advance(.05);
            if(c.view.savedPlay.result.reason!=='gameover')throw Error('end');await c.close();
          }
          for(const profile of ['student','test']) {
            const p=await buy({profile,characterId:'bear'}),c=await openRunnerSession(profile,p.id,{lifecycle:false});
            await c.resume();await c.jump();await c.advance(.25);await c.close();
          }
          const before=await snapshotAllStores();
          await replaceAllStores(validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:before}));
          if(JSON.stringify(before)!==JSON.stringify(await snapshotAllStores()))throw Error('mixed roundtrip');
          for(const version of [1,9]) {
            const old=plushFixture([], 'test');delete old.runnerPlays;
            await replaceAllStores(validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:version,data:old}));
            if((await readAll('runnerPlays')).length)throw Error('old backup');
          }
          for(const stageId of ['S05','S06']) {
            await plushInstall(plushFixture([], 'test'));
            // Student unlocks still come from preceding clears; test can select all stages.
            await runnerTransaction(['runnerPlays'],tx=>{
              for(const [i,characterId] of ['shiba','sloth','goldfish','salamander'].entries()) {
                // IndexedDB returns random UUID key order, not character order.
                const old=before.runnerPlays.find(p=>p.status==='finished'&&p.characterId===characterId);
                tx.objectStore('runnerPlays').put({...old,id:'unlock-'+characterId,stageId:'S0'+(i+1),result:{...old.result,reason:'clear',livesRemaining:1}});
              }
              const old=before.runnerPlays.find(p=>p.status==='finished');
              tx.objectStore('runnerPlays').put({...old,id:'unlock5',stageId:'S05',result:{...old.result,reason:'clear',livesRemaining:1}});
            });
            for(const profile of ['student','test']) {
              const p=await buy({profile,stageId,characterId:'bear'});
              if(p.stageVersion!==8)throw Error('version');
              const c=await openRunnerSession(profile,p.id,{lifecycle:false});await c.resume();await c.advance(.5);await c.jump();await c.advance(.25);await c.pause();
              const snap=m.snapshotRunner(c.view.state);await c.close();
              const r=await openRunnerSession(profile,p.id,{lifecycle:false});
              if(JSON.stringify(m.snapshotRunner(r.view.state))!==JSON.stringify(snap))throw Error('latest restore');
              await r.resume();await r.advance(.1);await r.close();
            }
          }
          return DB_VERSION===10&&BACKUP_VERSION===10&&(await readAll('runnerPlays')).filter(p=>p.status==='active').every(p=>p.snapshot.version===2);
        }'''))


class RunnerBearUITest(unittest.TestCase):
    setUpClass = classmethod(integration.RunnerIntegrationTest.setUpClass.__func__)
    tearDownClass = classmethod(integration.RunnerIntegrationTest.tearDownClass.__func__)
    setUp = integration.RunnerIntegrationTest.setUp
    tearDown = integration.RunnerIntegrationTest.tearDown
    enter = integration.RunnerIntegrationTest.enter

    def test_bear_page_reload_free_resume_and_four_viewports(self):
        self.enter()
        self.page.locator('#formal-character-cards [data-choice="bear"]').click()
        self.assertIn('記録なし',self.page.locator('#runner-character-bests .is-selected').inner_text())
        self.assertTrue(self.page.locator('[data-choice="secret-locked"]').is_disabled())
        for w,h in [(390,844),(844,390),(1024,768),(507,768)]:
            self.page.set_viewport_size(dict(width=w,height=h))
            card=self.page.locator('#formal-character-cards [data-choice="bear"]');card.scroll_into_view_if_needed()
            self.assertEqual(card.get_attribute('aria-pressed'),'true')
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            for box in self.page.locator('#formal-character-cards button').evaluate_all('bs=>bs.map(b=>{const r=b.getBoundingClientRect();return [r.width,r.height]})'):
                self.assertGreaterEqual(min(box),44)
            self.page.evaluate("document.documentElement.style.fontSize='200%'")
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            self.page.evaluate("document.documentElement.style.fontSize=''")
        self.page.set_viewport_size(dict(width=390,height=844))
        frame=self.page.frame_locator('iframe');frame.locator('#runner-toggle').scroll_into_view_if_needed()
        self.page.once('dialog',lambda d:d.accept());frame.locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session?.view.state.mode==='running'")
        frame.locator('#runner-toggle').filter(has_text='一時停止').wait_for()
        frame.locator('#runner-jump').click();frame.locator('#runner-toggle').click()
        frame.locator('#runner-toggle').filter(has_text='再開').wait_for()
        self.page.wait_for_function("formalRunner.session.view.state.mode==='paused'&&!formalRunner.session.view.dirty")
        before=self.page.evaluate('formalRunner.session.view.state.distance')
        self.page.reload();self.page.wait_for_function('appReady')
        if self.page.locator('#open-runner').is_visible():
            self.enter()
        frame=self.page.frame_locator('iframe');frame.locator('#runner-toggle').filter(has_text='再開').wait_for()
        self.assertAlmostEqual(self.page.evaluate('formalRunner.session.view.state.distance'),before)
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,formalRunner.session.view.state.characterId,formalRunner.session.view.state.initialLives]"),[1,'bear',3])
        frame.locator('#runner-toggle').click()
        self.page.wait_for_function("formalRunner.session.view.state.mode==='running'")
        self.assertEqual(self.page.evaluate("async()=>(await readAll('coinSpends')).length"),1)


if __name__=='__main__':
    unittest.main()
