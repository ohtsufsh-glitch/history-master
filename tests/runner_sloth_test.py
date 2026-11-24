"""Sloth tuning: motion and paid snapshot compatibility; synthetic local data only."""
import re
import subprocess
import unittest

import runner_session_test as sessions


BASE = '25f570f3175c81ad58caec9bdaf456a047b9b8dc'


class RunnerSlothTest(unittest.TestCase):
    setUpClass = classmethod(sessions.RunnerSessionTest.setUpClass.__func__)
    tearDownClass = classmethod(sessions.RunnerSessionTest.tearDownClass.__func__)
    setUp = sessions.RunnerSessionTest.setUp
    tearDown = sessions.RunnerSessionTest.tearDown

    def old_catalog(self):
        source = subprocess.check_output(
            ['git', 'show', f'{BASE}:runner/characters.js'],
            cwd=sessions.plush.ROOT, text=True)
        self.page.route('**/runner/sloth-baseline.js', lambda route: route.fulfill(
            content_type='text/javascript', body=source))
        self.page.evaluate("async()=>{window.oldCatalog=await import('./runner/sloth-baseline.js');}")

    def test_speed_jump_elapsed_positions_and_landing(self):
        rows = self.page.evaluate('''()=>{
          const rows=[];
          for(const hz of [30,60,120]) {
            const s=m.createRunnerState([],'sloth');s.mode='running';m.startJump(s);
            if(m.startJump(s))throw Error('extra jump');
            const samples=[];
            for(let frame=1;frame<=5.5*hz;frame++) {
              m.updateRunner(s,1/hz);
              const t=frame/hz,expectedY=470-(4*125/5.5)*t+(8*125/5.5**2)*t*t/2;
              if(Math.abs(s.elapsed-t)>1e-8||Math.abs(s.distance-34*t)>1e-7||
                Math.abs(s.feetY-expectedY)>1e-7)throw Error('trajectory '+hz+' '+t);
              if(frame<5.5*hz&&s.supportId!==null)throw Error('early landing');
              if(frame===hz||frame===5.5*hz)samples.push(m.snapshotRunner(s));
            }
            const apex=m.createRunnerState([],'sloth');apex.mode='running';m.startJump(apex);
            m.updateRunner(apex,2.75);
            rows.push({hz,speed:s.speed,jump:s.jump,lives:s.initialLives,air:s.airJumpsRemaining,
              apex:470-apex.feetY,apexVelocity:apex.velocityY,samples,
              landing:[s.supportId,s.feetY,s.velocityY,s.airAction,m.characterPose(s)]});
          }return rows;
        }''')
        for row in rows:
            self.assertEqual([row['speed'], row['lives'], row['air']], [34, 2, 0])
            self.assertEqual([row['jump'][k] for k in ['height', 'duration']], [125, 5.5])
            self.assertAlmostEqual(row['apex'], 125, places=7)
            self.assertAlmostEqual(row['apexVelocity'], 0, places=7)
            self.assertEqual(row['landing'], ['ground', 470, 0, None, 'land'])
            self.assertAlmostEqual(row['samples'][0]['distance'], 34, places=7)
            self.assertAlmostEqual(row['samples'][-1]['elapsed'], 5.5, places=7)

    def test_other_definitions_unchanged_and_display_and_delivery_versions(self):
        self.old_catalog()
        self.assertTrue(self.page.evaluate('''()=>{
          for(const id of ['shiba','goldfish','salamander','bear','secret_yuniko'])
            if(JSON.stringify(m.getCharacter(id))!==JSON.stringify(oldCatalog.getCharacter(id)))return false;
          const text=m.describeCharacter(m.getCharacter('sloth'));
          return text.includes('走力：低')&&text.includes('ジャンプ：中')&&
            text.includes('とてもゆっくり走って、長くジャンプ');
        }'''))
        root = sessions.plush.ROOT
        version = re.search(r'const APP_VERSION = "v([\d.]+)";', (root/'index.html').read_text())[1]
        for name in ['index.html', 'runner/index.html', 'runner/game.js']:
            identifiers = re.findall(r'[?&]v=([\d.]+)', (root/name).read_text())
            self.assertTrue(identifiers, name)
            self.assertEqual(set(identifiers), {version}, name)

    def test_new_paid_jump_save_reload_resume_matches_continuous_motion(self):
        self.page.evaluate('''async()=>{
          const p=await buy({characterId:'sloth'});
          const c=await openRunnerSession('student',p.id,{lifecycle:false});
          await c.resume();await c.jump();await c.advance(1.375);await c.pause();
          window.checkpoint=m.snapshotRunner(c.view.state);window.playId=p.id;await c.close();
        }''')
        checkpoint = self.page.evaluate('checkpoint')
        play_id = self.page.evaluate('playId')
        self.page.reload()
        self.page.wait_for_function('appReady')
        self.assertTrue(self.page.evaluate('''async({checkpoint,id})=>{
          const m=await loadRunnerModel(),c=await openRunnerSession('student',id,{lifecycle:false});
          if(JSON.stringify(m.snapshotRunner(c.view.state))!==JSON.stringify(checkpoint))throw Error('reload');
          const control=m.createRunnerState(m.getStage('S01',c.view.savedPlay.stageVersion),'sloth');control.mode='running';m.startJump(control);
          m.updateRunner(control,1.375);await c.resume();
          for(let i=0;i<165;i++){m.updateRunner(control,.025);await c.advance(.025);}
          await c.pause();control.mode='paused';
          if(JSON.stringify(m.snapshotRunner(control))!==JSON.stringify(m.snapshotRunner(c.view.state)))
            throw Error('resume drift '+JSON.stringify([m.snapshotRunner(control),m.snapshotRunner(c.view.state)]));
          await c.close();const records=await readAll('runnerPlays'),spends=await readAll('coinSpends');
          validateRunnerPlays(records);
          return c.view.state.supportId==='ground'&&records.length===1&&spends.length===1&&spends[0].amount===30&&
            DB_VERSION===10&&BACKUP_VERSION===10&&records[0].snapshot.version===2;
        }''', dict(checkpoint=checkpoint, id=play_id)))

    def test_old_paid_ground_and_airborne_records_retained_with_known_physics_change(self):
        self.old_catalog()
        rows = self.page.evaluate('''async()=>{
          const rows=[];
          for(const phase of ['ground','ascending','apex','descending']) {
            await install(30);const p=await buy({characterId:'sloth'});
            const s=m.createRunnerState(m.getStage('S01',p.stageVersion),'sloth'),old=oldCatalog.getCharacter('sloth');
            s.speed=old.speed;s.jump=old.jump;s.mode='running';
            if(phase!=='ground'){m.startJump(s);m.updateRunner(s,{ascending:.275,apex:.55,descending:.825}[phase]);}
            else m.updateRunner(s,.2);
            s.mode='paused';p.snapshot=m.snapshotRunner(s);p.score=s.score;
            await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').put(p));
            const before=JSON.stringify(await readAll('runnerPlays'));
            const c=await openRunnerSession('student',p.id,{lifecycle:false});
            if(before!==JSON.stringify(await readAll('runnerPlays')))throw Error('record rewritten on open');
            const restored=m.snapshotRunner(c.view.state);
            if(JSON.stringify(restored)!==JSON.stringify(p.snapshot))throw Error('snapshot converted');
            const oldNext=structuredClone(s);oldNext.mode='running';m.updateRunner(oldNext,.1);
            await c.resume();await c.advance(.1);await c.pause();
            rows.push({phase,speed:c.view.state.speed,gravity:c.view.state.jump.gravity,
              oldVelocity:restored.velocityY,y:c.view.state.feetY,oldY:oldNext.feetY,
              advance:c.view.state.distance-s.distance});
            const records=await readAll('runnerPlays');validateRunnerPlays(records);
            if(records.length!==1||records[0].id!==p.id||records[0].snapshot.version!==2||
              (await readAll('coinSpends')).length!==1)throw Error('record/charge lost');
            await c.close();
          }return rows;
        }''')
        for row in rows:
            self.assertEqual(row['speed'], 34)
            self.assertAlmostEqual(row['advance'], 3.4, places=7)
            self.assertAlmostEqual(row['gravity'], 1000/5.5**2, places=7)
            if row['phase'] == 'ground':
                self.assertEqual(row['y'], row['oldY'])
            else:
                self.assertAlmostEqual(row['y']-row['oldY'], (1000/5.5**2-1000/1.1**2)*.1**2/2, places=7)


if __name__ == '__main__':
    unittest.main()
