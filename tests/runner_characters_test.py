"""Issue #79/#81: 固定配置・4匹の物理・自動継続・残機・しば犬の互換性。

4匹×6ステージ×60/120Hz。攻略は開始とジャンプ入力だけで、位置・得点・
無敵状態を書き換えない。Chromium/WebKit共通、Safari実機とは区別する。
"""

import unittest

import runner_canvas_test as canvas
import runner_preview_test as preview
from runner_difficulty_cases import EXPECTED, SOLUTIONS, character_inputs


# 変更前main 663585b8e881317f330bcd69f800be0edd43dc96 の全フレームの記録。
# 各行は60Hz完全取得、120Hz完全取得のSHA256。
# Issue #84で配置を変更したS02〜S06は設計値・実入力の検証に置換。
# 衝突時の変更はIssue #81で意図したため旧衝突トレースは比較対象外。
# しば犬の位置・足場・ジャンプ・姿勢・得点を1e-6px/秒で比較する。
BASELINE_TRACES = {
    'legacy': (
        '99918fad5e7523d82be12cf367f9a609d4a8f9280fa22d1f8df7c8c96cb5c99d',
        '9e29f2d904a84c0513ccdf098ce06e4286888488a2d1a18a965f34cfc5fbeb09'),
    'S01': (
        '14279221e53aae9167b5ffdc55de02a4542f248f7db3a9c277d077870f59a8ea',
        '15af906f435c141a3d4a6384202c29615af5bfb2eb6cb202cae6aee5af5aadcd'),

}

SHIBA_TRACE = """({stageId,hz,path,solutions})=>{
  const m=runnerModel,stage=stageId==='legacy'?m.COURSE:runnerStages.find(s=>s.stageId===stageId);
  const s=m.createRunnerState(stage),trace=[];s.mode='running';let next=0;
  const inputs=stageId==='legacy'?Array.from({length:8},(_,i)=>5.61+i*3-.45):solutions[stageId].perfect;
  function sample(){
    const keys=['mode','lives','distance','elapsed','animationTime','feetY','velocityY',
      'supportId','jumpOriginY','airAction','landingUntil','score','reason','nextSpawn',
      'invincibleRemaining'];
    const snap=Object.fromEntries(keys.map(k=>[k,s[k]]));
    snap.objects=s.objects.map(o=>({at:o.at,type:o.type,height:o.height??null,id:o.id,x:o.x}));
    snap.pose=m.characterPose(s);snap.center=m.characterCenter(s);
    return JSON.parse(JSON.stringify(snap,(_,v)=>typeof v==='number'?Math.round(v*1e6)/1e6:v));
  }
  trace.push(sample());
  for(let f=0;f<hz*50&&s.mode!=='finished';f++){
    if(path==='perfect'&&next<inputs.length&&f/hz+1e-9>=inputs[next]){
      m.startJump(s);next++;
    }
    m.updateRunner(s,1/hz);trace.push(sample());
  }
  return trace;
}"""


class RunnerCharactersTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    open_runner = canvas.RunnerCanvasTest.open_runner
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    model_runner = canvas.RunnerCanvasTest.model_runner
    # The original 48-way suite is retained for frozen v1; phase1 has representative routes.
    def preview_runner(self, *args, **kwargs):
        return preview.RunnerPreviewTest.preview_runner(self, *args, legacy_catalog=True, **kwargs)
    settle = preview.RunnerPreviewTest.settle

    def character_runner(self):
        page, errors, requests = self.model_runner()
        page.evaluate("async()=>{window.runnerStages=(await import('./stages.js')).LEGACY_STAGES;}")
        return page, errors, requests

    def assert_isolated(self, page, errors, requests):
        self.assertEqual(errors, [])
        self.assertEqual(page.evaluate('runnerStorageAccesses'), [])
        prefix = self.url.removesuffix('runner/') + 'assets/plush/'
        self.assertTrue(all(url.startswith(self.url) or url.startswith(prefix) for url in requests), requests)

    def test_catalog_and_character_specific_jump_at_60_and_120_hz(self):
        page, errors, requests = self.character_runner()
        actual = page.evaluate("""()=>{
          const m=runnerModel,results=[];
          for(const c of m.CHARACTERS)for(const hz of [60,120]){
            const s=m.createRunnerState([],c.characterId);s.mode='running';
            const accepted=m.startJump(s),before=JSON.stringify(s);
            const repeated=m.startJump(s),repeatedStable=before===JSON.stringify(s);
            m.updateRunner(s,c.jump.duration/2);
            const apex={height:m.GROUND_Y-s.feetY,velocity:s.velocityY};
            m.updateRunner(s,c.jump.duration/2);
            const landed={feet:s.feetY,support:s.supportId,velocity:s.velocityY};
            const natural=m.createRunnerState([],c.characterId);natural.mode='running';m.startJump(natural);
            let highest=0,landingTime=null;
            for(let f=1;f<=Math.ceil(c.jump.duration*hz)+1;f++){
              m.updateRunner(natural,1/hz);highest=Math.max(highest,m.GROUND_Y-natural.feetY);
              if(natural.supportId==='ground'){landingTime=f/hz;break;}
            }
            const retry=m.createRunnerState(s);
            results.push({id:c.characterId,hz,speed:s.speed,height:s.jump.height,duration:s.jump.duration,
              lives:s.initialLives,accepted,repeated,repeatedStable,apex,landed,highest,landingTime,
              retry:{id:retry.characterId,lives:retry.lives,distance:retry.distance,score:retry.score},
              frozen:Object.isFrozen(c)&&Object.isFrozen(c.jump)&&Object.isFrozen(c.image)});
          }
          return {results,defaultId:m.createRunnerState().characterId,
            invalid:['unknown',''].map(id=>{try{m.createRunnerState([],id);return false;}
              catch(e){return e instanceof TypeError;}})};
        }""")
        expected = {'shiba': (200, 120, .9, 2), 'sloth': (170, 125, 1.1, 2),
                    'goldfish': (185, 160, 1.05, 2), 'salamander': (230, 105, .82, 3), 'bear': (180, 130, 1.00, 3)}
        self.assertEqual(actual['defaultId'], 'shiba')
        self.assertTrue(all(actual['invalid']))
        self.assertEqual(len(actual['results']), 10)
        for row in actual['results']:
            with self.subTest(character=row['id'], hz=row['hz']):
                speed, height, duration, lives = expected[row['id']]
                self.assertEqual((row['speed'], row['height'], row['duration'], row['lives']),
                                 (speed, height, duration, lives))
                self.assertTrue(row['accepted'] and row['repeatedStable'] and row['frozen'])
                self.assertFalse(row['repeated'])
                self.assertAlmostEqual(row['apex']['height'], height, delta=1e-6)
                self.assertAlmostEqual(row['apex']['velocity'], 0, delta=1e-6)
                self.assertEqual(row['landed'], {'feet': 470, 'support': 'ground', 'velocity': 0})
                self.assertAlmostEqual(row['highest'], height, delta=.1)
                self.assertAlmostEqual(row['landingTime'], duration, delta=1/row['hz'] + 1e-6)
                self.assertEqual(row['retry'], {'id': row['id'], 'lives': lives, 'distance': 0, 'score': 0})
        self.assert_isolated(page, errors, requests)

    def test_all_characters_clear_100_and_keep_world_positions_at_60_and_120_hz(self):
        # Frozen four-character routes below deliberately exclude later additions.
        page, errors, requests = self.character_runner()
        outcomes = page.evaluate("""solutions=>{
          const m=runnerModel,results=[];
          for(const c of m.CHARACTERS.slice(0,4))for(const stage of runnerStages)for(const hz of [60,120]){
            const s=m.createRunnerState(stage,c.characterId);s.mode='running';
            const inputs=solutions[c.characterId][stage.stageId];
            let next=0,maxPositionError=0,wrongSpawns=0,maxShield=0;const accepted=[],seen=new Set(),landings=new Set();
            for(let f=0;f<hz*60&&s.mode==='running';f++){
              if(next<inputs.length&&f/hz+1e-9>=inputs[next]){accepted.push(m.startJump(s));next++;}
              m.updateRunner(s,1/hz);
              maxShield=Math.max(maxShield,s.invincibleRemaining);
              for(const o of s.objects){
                seen.add(o.id);
                // 独立した200px/s基準。新しい速度やspawnDistance自身から正解を作らない。
                maxPositionError=Math.max(maxPositionError,Math.abs(o.x+s.distance-(1008+o.at*200)));
                if(o.spawnDistance!==o.at*200||s.distance+1e-6<o.at*200)wrongSpawns++;
              }
              if(s.supportId!==null&&s.supportId!=='ground')landings.add(s.supportId);
            }
            const ended=JSON.stringify(s);m.updateRunner(s,100);const endJump=m.startJump(s);
            results.push({character:c.characterId,stage:stage.stageId,hz,mode:s.mode,reason:s.reason,
              distance:s.distance,elapsed:s.elapsed,score:s.score,lives:s.lives,next,accepted,
              progress:m.progressPercent(s),landings:landings.size,maxPositionError,wrongSpawns,maxShield,
              seen:seen.size,events:stage.course.length,goal:m.goalX(s),
              frozen:ended===JSON.stringify(s),endJump});
          }
          return results;
        }""", {c: {key: character_inputs(key, speed, duration)
            for key in EXPECTED} for c, speed, duration in
            [('shiba',200,.90),('sloth',170,1.10),('goldfish',185,1.05),('salamander',230,.82)]})
        self.assertEqual(len(outcomes), 48)
        speeds = {'shiba': 200, 'sloth': 170, 'goldfish': 185, 'salamander': 230}
        for row in outcomes:
            with self.subTest(character=row['character'], stage=row['stage'], hz=row['hz']):
                spec = EXPECTED[row['stage']]
                self.assertEqual((row['mode'], row['reason'], row['progress'], row['score']),
                                 ('finished', 'clear', 100, 100), row)
                self.assertEqual(row['lives'], 3 if row['character'] == 'salamander' else 2)
                self.assertEqual(row['maxShield'], 0)
                self.assertTrue(all(row['accepted']), row)
                self.assertEqual(row['next'], len(character_inputs(row['stage'], speeds[row['character']],
                    {'shiba':.9,'sloth':1.1,'goldfish':1.05,'salamander':.82}[row['character']])))
                self.assertGreaterEqual(row['landings'], len(spec['upper']))
                self.assertEqual(row['distance'], spec['length'])
                self.assertAlmostEqual(row['elapsed'], spec['length']/speeds[row['character']], delta=1e-6)
                self.assertAlmostEqual(row['goal'], 186, delta=1e-6)
                self.assertLess(row['maxPositionError'], 1e-6)
                self.assertEqual(row['wrongSpawns'], 0)
                self.assertEqual(row['seen'], row['events'])
                self.assertTrue(row['frozen'])
                self.assertFalse(row['endJump'])
        self.assert_isolated(page, errors, requests)

    def test_every_stage_collisions_auto_continue_and_initial_lives_at_both_rates(self):
        page, errors, requests = self.character_runner()
        outcomes = page.evaluate("""()=>{
          const m=runnerModel,results=[];
          for(const c of m.CHARACTERS.slice(0,4))for(const stage of runnerStages)for(const hz of [60,120]){
            const s=m.createRunnerState(stage,c.characterId),checks=[];s.mode='running';
            let stopped=false,lastHit=-Infinity;
            for(let f=0;f<hz*60&&s.mode!=='finished';f++){
              const beforeLives=s.lives,beforeDistance=s.distance,beforeElapsed=s.elapsed;
              m.updateRunner(s,1/hz);
              if(s.mode!=='running'&&s.mode!=='finished')stopped=true;
              if(s.lives<beforeLives){
                checks.push({lives:s.lives,mode:s.mode,oneLife:beforeLives-s.lives===1,
                  moving:s.distance>beforeDistance&&s.elapsed>beforeElapsed,
                  shield:s.invincibleRemaining,spacing:s.elapsed-lastHit});
                lastHit=s.elapsed;
              }
            }
            const end=JSON.stringify(s);m.updateRunner(s,100);m.startJump(s);
            const retry=m.createRunnerState(s);
            results.push({character:c.characterId,stage:stage.stageId,hz,checks,stopped,
              reason:s.reason,lives:s.lives,score:s.score,frozen:end===JSON.stringify(s),
              retry:{id:retry.characterId,stage:retry.stageId,lives:retry.lives,score:retry.score,
                distance:retry.distance,elapsed:retry.elapsed,shield:retry.invincibleRemaining}});
          }
          return results;
        }""")
        self.assertEqual(len(outcomes), 48)
        for row in outcomes:
            with self.subTest(character=row['character'], stage=row['stage'], hz=row['hz']):
                lives = 3 if row['character'] == 'salamander' else 2
                collisions = min(lives, len(EXPECTED[row['stage']]['rocks']))
                self.assertEqual(len(row['checks']), collisions)
                self.assertFalse(row['stopped'])
                self.assertEqual(row['lives'], lives-collisions)
                self.assertEqual(row['reason'], 'clear' if collisions < lives else 'collision')
                for i, hit in enumerate(row['checks']):
                    self.assertEqual(hit['lives'], lives-i-1)
                    self.assertTrue(hit['oneLife'] and hit['moving'])
                    self.assertGreater(hit['spacing'], 1)
                    self.assertEqual(hit['mode'], 'running' if hit['lives'] else 'finished')
                    if hit['lives']:
                        self.assertGreaterEqual(hit['shield'], 1-1/row['hz']-1e-9)
                        self.assertLessEqual(hit['shield'], 1)
                self.assertLessEqual(row['score'], 100)
                self.assertTrue(row['frozen'])
                self.assertEqual(row['retry'], {'id': row['character'], 'stage': row['stage'],
                    'lives': lives, 'score': 0, 'distance': 0, 'elapsed': 0, 'shield': 0})
        self.assert_isolated(page, errors, requests)

    def test_shield_boundary_pause_jump_stars_and_repeated_contacts_at_both_rates(self):
        page, errors, requests = self.character_runner()
        outcomes = page.evaluate("""()=>{
          const m=runnerModel,results=[];
          for(const c of m.CHARACTERS.slice(0,4))for(const hz of [60,120]){
            const s=m.createRunnerState([],c.characterId);s.mode='running';
            s.objects=[{id:'rock-a',type:'obstacle',x:186},{id:'rock-b',type:'obstacle',x:186}];
            m.updateRunner(s,0);
            const first={lives:s.lives,mode:s.mode,shield:s.invincibleRemaining};
            s.mode='paused';const paused=JSON.stringify(s);
            m.updateRunner(s,100);const pausedJump=m.startJump(s);
            const pauseStable=paused===JSON.stringify(s),resumed=m.resumeRunner(s);
            const resumedShield=s.invincibleRemaining,resumedState=JSON.stringify(s);
            const doubleResume=m.resumeRunner(s),doubleStable=resumedState===JSON.stringify(s);
            const jump=m.startJump(s);
            m.updateRunner(s,c.jump.duration/2);
            const apex=m.GROUND_Y-s.feetY;
            s.objects.push({id:'protected-star',type:'star',x:186,height:apex});
            m.updateRunner(s,0);const score=s.score;
            m.updateRunner(s,0);const noDuplicate=s.score===score;
            // 新規の近接岩を毎フレーム配置。ちょうど1秒までは再減算しない。
            let sameLives=true,remaining=1-c.jump.duration/2;
            while(remaining>1e-9){
              for(const o of s.objects)if(o.type==='obstacle')o.x=186;
              const step=Math.min(1/hz,remaining);m.updateRunner(s,step);remaining-=step;
              sameLives&&=s.lives===first.lives&&s.mode==='running';
            }
            const expired=s.invincibleRemaining;
            // 着地を待つ必要のない地上の対照stateで解除直後の接触を確認。
            const ground=m.createRunnerState([],c.characterId);ground.mode='running';
            ground.objects=[{id:'boundary-rock',type:'obstacle',x:186}];m.updateRunner(ground,0);
            for(let f=0;f<hz;f++){
              ground.objects[0].x=186;m.updateRunner(ground,1/hz);
            }
            const boundary={lives:ground.lives,mode:ground.mode,shield:ground.invincibleRemaining};
            ground.objects[0].x=186;m.updateRunner(ground,1/hz);
            const after={lives:ground.lives,mode:ground.mode,shield:ground.invincibleRemaining};
            results.push({id:c.characterId,hz,first,pausedJump,pauseStable,resumed,resumedShield,
              doubleResume,doubleStable,jump,apex,score,noDuplicate,sameLives,expired,boundary,after});
          }
          return results;
        }""")
        for row in outcomes:
            with self.subTest(character=row['id'], hz=row['hz']):
                lives = 3 if row['id'] == 'salamander' else 2
                self.assertEqual(row['first'], {'lives': lives-1, 'mode': 'running', 'shield': 1})
                self.assertFalse(row['pausedJump'] or row['doubleResume'])
                for key in ('pauseStable','resumed','doubleStable','jump','noDuplicate','sameLives'):
                    self.assertTrue(row[key], (key,row))
                self.assertEqual(row['resumedShield'], 1)
                self.assertGreater(row['apex'], 100)
                self.assertEqual(row['score'], 10)
                self.assertAlmostEqual(row['expired'], 0, delta=1e-9)
                self.assertEqual((row['boundary']['lives'],row['boundary']['mode']), (lives-1,'running'))
                self.assertAlmostEqual(row['boundary']['shield'], 0, delta=1e-9)
                self.assertEqual((row['after']['lives'],row['after']['mode']),
                                 (lives-2,'running' if lives>2 else 'finished'))
        self.assert_isolated(page, errors, requests)

    def test_preview_controls_clear_all_48_character_stage_frame_rate_combinations(self):
        page, errors, requests = self.preview_runner()
        characters = {'shiba': (200, .90, 2), 'sloth': (170, 1.10, 2),
                      'goldfish': (185, 1.05, 2), 'salamander': (230, .82, 3)}
        for character_id, (speed, duration, lives) in characters.items():
            page.locator('#runner-character-select').select_option(character_id)
            page.wait_for_function('runnerImages.every(image=>image.complete)', polling=50)
            self.settle(page)
            for stage_id, spec in EXPECTED.items():
                inputs = character_inputs(stage_id, speed, duration)
                for hz in (60, 120):
                    with self.subTest(character=character_id, stage=stage_id, hz=hz):
                        # 実画面のchange/clickと描画RAFのみ。状態は読み取り専用で使う。
                        outcome = page.evaluate("""({stageId,hz,inputs})=>{
                          const select=document.querySelector('#runner-stage-select');
                          select.value=stageId;select.dispatchEvent(new Event('change',{bubbles:true}));
                          const toggle=document.querySelector('#runner-toggle');toggle.click();
                          const start=runnerClock.snapshot().now;runnerClock.step(start);
                          const jump=document.querySelector('#runner-jump'),accepted=[];let next=0;
                          for(let f=0;f<hz*60&&runnerPreviewState.mode==='running';f++){
                            if(next<inputs.length&&f/hz+1e-9>=inputs[next]){
                              const grounded=runnerPreviewState.supportId!==null;
                              jump.click();accepted.push(grounded&&runnerPreviewState.supportId===null);next++;
                            }
                            runnerClock.step(start+(f+1)*1000/hz);
                          }
                          const s=runnerPreviewState;
                          return {character:s.characterId,stage:s.stageId,mode:s.mode,reason:s.reason,
                            score:s.score,lives:s.lives,distance:s.distance,accepted,next,
                            result:document.querySelector('#runner-result-title').textContent,
                            resultScore:document.querySelector('#runner-result-score').textContent,
                            hud:document.querySelector('#runner-hearts').textContent,
                            livesLabel:document.querySelector('#runner-lives').getAttribute('aria-label'),
                            progress:document.querySelector('#runner-progress').textContent};
                        }""", dict(stageId=stage_id, hz=hz, inputs=inputs))
                        self.assertEqual((outcome['character'], outcome['stage']), (character_id, stage_id))
                        self.assertEqual((outcome['mode'], outcome['reason'], outcome['score']),
                                         ('finished', 'clear', 100), outcome)
                        self.assertEqual(outcome['lives'], lives)
                        self.assertEqual(outcome['distance'], spec['length'])
                        self.assertTrue(all(outcome['accepted']), outcome)
                        self.assertEqual(outcome['next'], len(inputs))
                        self.assertEqual((outcome['result'], outcome['resultScore'], outcome['progress'],
                                          outcome['hud']), ('クリア！', '100', '100', '♥'*lives))
                        self.assertEqual(outcome['livesLabel'], f'残機{lives}機中あと{lives}機')
        self.assert_isolated(page, errors, requests)

    def test_shiba_full_frame_traces_match_unchanged_main_course_and_all_stages(self):
        page, errors, requests = self.character_runner()
        for stage_id, digests in BASELINE_TRACES.items():
            for i, hz in enumerate((60, 120)):
                path = 'perfect'
                with self.subTest(stage=stage_id, hz=hz, path=path):
                    script = 'async args=>{const trace=(' + SHIBA_TRACE + """)(args);
                      const bytes=new TextEncoder().encode(JSON.stringify(trace));
                      const digest=await crypto.subtle.digest('SHA-256',bytes);
                      return Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('');
                    }"""
                    digest = page.evaluate(script, dict(stageId=stage_id, hz=hz,
                                                        path=path, solutions=SOLUTIONS))
                    self.assertEqual(digest, digests[i])
        self.assert_isolated(page, errors, requests)


if __name__ == '__main__':
    unittest.main()
