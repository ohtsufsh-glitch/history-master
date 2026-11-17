"""6固定ステージを、配信されるゲームの物理・入力・描画で検証する。

実行: python3 -m unittest discover -s tests -p 'runner_stages_test.py' -v
HISTORY_MASTER_ENGINE=webkit でWebKitも実行できる。Safari実機確認は別途必要。
"""

import unittest

import runner_canvas_test as canvas


from runner_difficulty_cases import DESIGN, EXPECTED, EXPECTED_NAMES, SOLUTIONS


class RunnerStagesTest(unittest.TestCase):
    # 既存のテストクラスを継承せず、共通のブラウザ・監視ヘルパーのみ再利用。
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    open_runner = canvas.RunnerCanvasTest.open_runner
    assert_isolated = canvas.RunnerCanvasTest.assert_isolated
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    model_runner = canvas.RunnerCanvasTest.model_runner
    snapshot = canvas.RunnerCanvasTest.snapshot
    toggle = canvas.RunnerCanvasTest.toggle
    tap = canvas.RunnerCanvasTest.tap
    assert_same_scene = canvas.RunnerCanvasTest.assert_same_scene

    def stage_runner(self):
        page, errors, requests = self.model_runner()
        page.evaluate("""async () => {
          window.runnerStages = (await import('./stages.js')).LEGACY_STAGES;
        }""")
        return page, errors, requests

    def test_custom_future_stage_and_invalid_goal_configuration(self):
        # カタログの件数やIDによらず追加でき、旧配列APIも維持する。
        # stages.js 未導入でも、実ゲームモジュール単独で実行可能。
        page, errors, requests = self.model_runner()
        actual = page.evaluate("""() => {
          const m=runnerModel,definition={stageId:'S99',name:'追加テスト',difficulty:7,
            goalDistance:1234,course:[]};
          const state=m.createRunnerState(definition);state.mode='running';
          m.updateRunner(state,1234/400);
          const half={distance:state.distance,progress:m.progressPercent(state),goal:m.goalX(state)};
          m.updateRunner(state,100);
          const finish={mode:state.mode,reason:state.reason,distance:state.distance,
            elapsed:state.elapsed,progress:m.progressPercent(state),goal:m.goalX(state)};
          const retry=m.createRunnerState(state),legacy=m.createRunnerState([]);
          const invalid=[null,{}, {course:[]}, {goalDistance:10},
            {goalDistance:10,course:{}},
            ...[0,-1,NaN,Infinity,'100'].map(goalDistance=>({goalDistance,course:[]}))];
          return {half,finish,retry:{stageId:retry.stageId,goalDistance:retry.goalDistance,
              mode:retry.mode,distance:retry.distance,score:retry.score,elapsed:retry.elapsed,
              course:retry.course,distinct:retry.course!==state.course,
              lives:retry.lives,invincibleRemaining:retry.invincibleRemaining},
            legacy:{stageId:legacy.stageId,goalDistance:legacy.goalDistance},
            rejected:invalid.map(value=>{try{m.createRunnerState(value);return false;}
              catch(error){return error instanceof TypeError;}})};
        }""")
        self.assertAlmostEqual(actual['half']['distance'], 617, delta=1e-6)
        self.assertEqual(actual['half']['progress'], 50)
        self.assertAlmostEqual(actual['half']['goal'], 186 + 617, delta=1e-6)
        self.assertEqual((actual['finish']['mode'], actual['finish']['reason'],
                          actual['finish']['progress']), ('finished', 'clear', 100))
        self.assertAlmostEqual(actual['finish']['distance'], 1234, delta=1e-6)
        self.assertAlmostEqual(actual['finish']['elapsed'], 1234 / 200, delta=1e-6)
        self.assertAlmostEqual(actual['finish']['goal'], 186, delta=1e-6)
        self.assertEqual(actual['retry'], {'stageId': 'S99', 'goalDistance': 1234,
            'mode': 'ready', 'distance': 0, 'score': 0, 'elapsed': 0, 'course': [], 'distinct': True,
            'lives': 2, 'invincibleRemaining': 0})
        self.assertEqual(actual['legacy'], {'stageId': None, 'goalDistance': 6400})
        self.assertTrue(all(actual['rejected']))
        self.assertEqual(len(actual['rejected']), 10)
        self.assert_isolated(page, errors, requests)

    def test_unique_metadata_counts_and_arrival_to_spawn_conversion(self):
        page, errors, requests = self.stage_runner()
        stages = page.evaluate('runnerStages')
        constants = page.evaluate("""() => {
          const m=runnerModel;
          return {spawn:m.SPAWN_X,character:m.CHARACTER_X,speed:m.SCROLL_SPEED,
            jumpHeight:m.JUMP.height,jumpDuration:m.JUMP.duration,
            platformHeight:m.PLATFORM.height,platformWidth:m.PLATFORM.width,groundY:m.GROUND_Y,
            delay:(m.SPAWN_X-m.CHARACTER_X)/m.SCROLL_SPEED};
        }""")
        self.assertEqual(constants, {'spawn': 1008, 'character': 186, 'speed': 200,
            'jumpHeight': 120, 'jumpDuration': .9, 'platformHeight': 80,
            'platformWidth': 190, 'groundY': 470, 'delay': 4.11})
        self.assertEqual([s['stageId'] for s in stages], list(EXPECTED))
        self.assertEqual(len({s['stageId'] for s in stages}), 6)
        self.assertEqual(len({s['goalDistance'] for s in stages}), 6)
        for difficulty, stage in enumerate(stages, 1):
            with self.subTest(stage=stage['stageId']):
                expected = EXPECTED[stage['stageId']]
                self.assertEqual(stage['name'], EXPECTED_NAMES[stage['stageId']])
                self.assertEqual(stage['difficulty'], difficulty)
                self.assertEqual(stage['goalDistance'], expected['length'])
                course = stage['course']
                self.assertEqual(len([e for e in course if e['type'] == 'star']), 10)
                self.assertTrue(all(e['at'] >= 0 for e in course))
                self.assertTrue(all(e['type'] in ('star', 'obstacle', 'platform', 'wall') for e in course))
                self.assertEqual([e['at'] for e in course], sorted(e['at'] for e in course))
                spec = DESIGN[stage['stageId']]
                for kind, targets in (
                    ('obstacle', [(x, None, None) for x in spec['rocks']]),
                    ('platform', spec['platforms']), ('wall', spec['walls']),
                    ('star', [(x, None, h) for x,h in spec['stars']]),
                ):
                    actual = [e for e in course if e['type'] == kind]
                    self.assertEqual(len(actual), len(targets))
                    for entry, (x, width, height) in zip(actual, targets):
                        self.assertAlmostEqual(entry['at']*200+822, x, delta=1e-9)
                        if width is not None:
                            self.assertEqual(entry['width'], width)
                        if height is not None:
                            self.assertEqual(entry['height'], height)
                # 最初の危険まで猶予があり、最後の岩通過後も安全なゴール区間。
                self.assertGreaterEqual(expected['rocks'][0] - 68 / 200, 5)
                self.assertGreater(stage['goalDistance'] / 200 - expected['rocks'][-1], 1)
        self.assert_isolated(page, errors, requests)

    def test_every_event_spawns_at_right_edge_then_moves_left(self):
        page, errors, requests = self.stage_runner()
        actual = page.evaluate("""() => {
          const m=runnerModel;
          return runnerStages.map(stage => ({id:stage.stageId, events:stage.course.map(entry => {
            // 他の物体との接触を避け、各イベントの出現位置を単独で検証。
            const state=m.createRunnerState({...stage, course:[entry]}); state.mode='running';
            m.updateRunner(state,entry.at-.001);
            const before=state.objects.length;
            m.updateRunner(state,.001);
            const spawn=state.objects.map(o=>({x:o.x,type:o.type,height:o.height??0}));
            m.updateRunner(state,.2);
            return {before,spawn,x:state.objects[0]?.x};
          })}));
        }""")
        for stage in actual:
            for index, event in enumerate(stage['events']):
                with self.subTest(stage=stage['id'], event=index):
                    self.assertEqual(event['before'], 0)
                    self.assertEqual(len(event['spawn']), 1)
                    self.assertAlmostEqual(event['spawn'][0]['x'], 1008, delta=1e-6)
                    self.assertAlmostEqual(event['x'], 968, delta=1e-6)
        self.assert_isolated(page, errors, requests)

    def test_stage_goal_progress_and_collision_priority_use_own_distance(self):
        page, errors, requests = self.stage_runner()
        outcomes = page.evaluate("""() => runnerStages.map(stage => {
          const m=runnerModel, state=m.createRunnerState({...stage,course:[]});
          state.mode='running'; m.updateRunner(state,stage.goalDistance/400);
          const halfway={distance:state.distance,progress:m.progressPercent(state),goal:m.goalX(state)};
          m.updateRunner(state,stage.goalDistance/400-.005);
          const before={mode:state.mode,progress:m.progressPercent(state),distance:state.distance};
          m.updateRunner(state,1);
          const complete={mode:state.mode,reason:state.reason,distance:state.distance,
            elapsed:state.elapsed,progress:m.progressPercent(state),goal:m.goalX(state)};
          const collision=m.createRunnerState({...stage,course:[]}); collision.mode='running';
          collision.distance=stage.goalDistance-1;
          collision.objects=[{id:'final-rock',type:'obstacle',x:186}];m.updateRunner(collision,.005);
          const fatal=m.createRunnerState({...stage,course:[]});fatal.mode='running';fatal.lives=1;
          fatal.distance=stage.goalDistance-1;
          fatal.objects=[{id:'final-rock',type:'obstacle',x:186},
            {id:'final-star',type:'star',x:186}];m.updateRunner(fatal,.005);
          return {id:stage.stageId,goalDistance:state.goalDistance,halfway,before,complete,
            collision:{mode:collision.mode,lives:collision.lives,reason:collision.reason,
              progress:m.progressPercent(collision)},
            fatal:{mode:fatal.mode,lives:fatal.lives,reason:fatal.reason,score:fatal.score,
              progress:m.progressPercent(fatal)}};
        })""")
        for result in outcomes:
            with self.subTest(stage=result['id']):
                length = EXPECTED[result['id']]['length']
                self.assertEqual(result['goalDistance'], length)
                self.assertAlmostEqual(result['halfway']['distance'], length / 2, delta=1e-6)
                self.assertEqual(result['halfway']['progress'], 50)
                self.assertAlmostEqual(result['halfway']['goal'], 186 + length / 2, delta=1e-6)
                self.assertEqual(result['before']['mode'], 'running')
                self.assertEqual(result['before']['progress'], 99)
                self.assertAlmostEqual(result['before']['distance'], length - 1, delta=1e-6)
                complete = result['complete']
                self.assertEqual((complete['mode'], complete['reason'], complete['progress']),
                                 ('finished', 'clear', 100))
                self.assertAlmostEqual(complete['distance'], length, delta=1e-6)
                self.assertAlmostEqual(complete['elapsed'], length / 200, delta=1e-6)
                self.assertAlmostEqual(complete['goal'], 186, delta=1e-6)
                self.assertEqual(result['collision'],
                    {'mode': 'finished', 'lives': 1, 'reason': 'clear', 'progress': 100})
                self.assertEqual(result['fatal'],
                    {'mode': 'finished', 'lives': 0, 'reason': 'collision', 'score': 0, 'progress': 100})
        self.assert_isolated(page, errors, requests)

    def test_all_stages_clear_and_score_100_using_legal_inputs_at_60_and_120_hz(self):
        page, errors, requests = self.stage_runner()
        outcomes = page.evaluate("""solutions => {
          const m=runnerModel, results=[];
          for(const stage of runnerStages)for(const hz of [60,120])for(const path of ['clear','perfect']) {
            const state=m.createRunnerState(stage);state.mode='running';
            const inputs=solutions[stage.stageId][path], accepted=[], platforms=new Set(); let next=0;
            for(let frame=0;frame<hz*(stage.goalDistance/m.SCROLL_SPEED+1)&&state.mode==='running';frame++) {
              if(next<inputs.length&&frame/hz+1e-9>=inputs[next]) {
                accepted.push(m.startJump(state));next++;
              }
              m.updateRunner(state,1/hz);
              if(state.supportId!==null&&state.supportId!=='ground')platforms.add(state.supportId);
            }
            const frozen=JSON.stringify(state);m.updateRunner(state,100);m.startJump(state);
            results.push({id:stage.stageId,hz,path,mode:state.mode,reason:state.reason,score:state.score,
              distance:state.distance,elapsed:state.elapsed,progress:m.progressPercent(state),
              next,accepted,landings:platforms.size,frozen:frozen===JSON.stringify(state)});
          }
          return results;
        }""", SOLUTIONS)
        self.assertEqual(len(outcomes), 24)
        for result in outcomes:
            with self.subTest(stage=result['id'], hz=result['hz'], path=result['path']):
                self.assertEqual((result['mode'], result['reason'], result['progress']),
                                 ('finished', 'clear', 100), result)
                self.assertAlmostEqual(result['distance'], EXPECTED[result['id']]['length'], delta=1e-6)
                self.assertAlmostEqual(result['elapsed'], EXPECTED[result['id']]['length'] / 200, delta=1e-6)
                self.assertEqual(result['next'], len(SOLUTIONS[result['id']][result['path']]))
                self.assertTrue(all(result['accepted']), result)
                self.assertTrue(result['frozen'])
                if result['path'] == 'perfect':
                    self.assertEqual(result['score'], 100)
                    self.assertGreaterEqual(result['landings'], len(EXPECTED[result['id']]['upper']))
        self.assert_isolated(page, errors, requests)

    def test_two_hazard_hits_auto_continue_and_freeze_on_every_stage_at_60_and_120_hz(self):
        page, errors, requests = self.stage_runner()
        results = page.evaluate("""() => {
          const results=[],m=runnerModel;
          for(const stage of runnerStages)for(const hz of [60,120]) {
            const state=m.createRunnerState(stage),ready=JSON.stringify(state);
            m.updateRunner(state,100);m.startJump(state);
            const readyFrozen=ready===JSON.stringify(state),initialLives=state.lives;
            state.mode='running';m.updateRunner(state,1);
            state.mode='paused';const paused=JSON.stringify(state);
            m.updateRunner(state,100);m.startJump(state);
            const pauseFrozen=paused===JSON.stringify(state),resumed=m.resumeRunner(state);
            while(state.mode==='running'&&state.lives===2)m.updateRunner(state,1/hz);
            const first={mode:state.mode,reason:state.reason,lives:state.lives,
              elapsed:state.elapsed,distance:state.distance,score:state.score};
            const invincible=state.invincibleRemaining;
            const started=JSON.stringify(state),doubleResume=m.resumeRunner(state);
            const doubleStable=started===JSON.stringify(state);
            for(let i=0;i<hz*.9;i++)m.updateRunner(state,1/hz);
            const protectedState={mode:state.mode,lives:state.lives,
              invincibleRemaining:state.invincibleRemaining};
            state.mode='paused';const shieldPause=JSON.stringify(state);
            m.updateRunner(state,100);
            const shieldFrozen=shieldPause===JSON.stringify(state);
            m.resumeRunner(state);
            while(state.mode==='running')m.updateRunner(state,1/hz);
            const ended=JSON.stringify(state);m.updateRunner(state,100);const endJump=m.startJump(state);
            const final={mode:state.mode,reason:state.reason,lives:state.lives,
              elapsed:state.elapsed,distance:state.distance,score:state.score};
            const retry=m.createRunnerState(state);
            results.push({id:stage.stageId,hz,initialLives,readyFrozen,pauseFrozen,first,
              resumed,invincible,doubleResume,doubleStable,protectedState,shieldFrozen,
              final,endJump,endFrozen:ended===JSON.stringify(state),
              retry:{id:retry.stageId,lives:retry.lives,invincibleRemaining:retry.invincibleRemaining,
                score:retry.score,distance:retry.distance,elapsed:retry.elapsed}});
          }
          return results;
        }""")
        self.assertEqual(len(results), 12)
        for result in results:
            with self.subTest(stage=result['id'], hz=result['hz']):
                self.assertEqual(result['initialLives'], 2)
                for frozen in ('readyFrozen', 'pauseFrozen', 'doubleStable', 'shieldFrozen', 'endFrozen'):
                    self.assertTrue(result[frozen], (frozen, result))
                first, final = result['first'], result['final']
                self.assertEqual((first['mode'], first['reason'], first['lives']), ('running', None, 1))
                self.assertGreater(first['score'], 0)
                self.assertTrue(result['resumed'])
                self.assertFalse(result['doubleResume'])
                self.assertAlmostEqual(result['invincible'], 1, delta=1/result['hz']+1e-9)
                self.assertEqual((result['protectedState']['mode'], result['protectedState']['lives']),
                                 ('running', 1))
                self.assertAlmostEqual(result['protectedState']['invincibleRemaining'], .1,
                                       delta=1/result['hz']+1e-9)
                self.assertEqual((final['mode'], final['reason'], final['lives']),
                                 ('finished', 'collision', 0))
                self.assertFalse(result['endJump'])
                spec = DESIGN[result['id']]
                hazards = sorted(spec['rocks'] + [x for x, _, _ in spec['walls']])
                for collision, arrival in ((first, hazards[0]/200), (final, hazards[1]/200)):
                    self.assertLess(collision['elapsed'], arrival)
                    self.assertGreater(collision['elapsed'], arrival - .5)
                self.assertEqual(result['retry'], {'id': result['id'], 'lives': 2,
                    'invincibleRemaining': 0, 'score': 0, 'distance': 0, 'elapsed': 0})
        for stage_id in EXPECTED:
            pair = [r for r in results if r['id'] == stage_id]
            for moment in ('first', 'final'):
                self.assertAlmostEqual(pair[0][moment]['elapsed'], pair[1][moment]['elapsed'], delta=1/60)
                self.assertAlmostEqual(pair[0][moment]['distance'], pair[1][moment]['distance'], delta=200/60)
        self.assert_isolated(page, errors, requests)

    def test_collision_preserves_motion_support_events_and_star_scoring(self):
        page, errors, requests = self.model_runner()
        outcomes = page.evaluate("""()=>{
          const m=runnerModel,results=[];
          const checkpoint=s=>JSON.stringify({...s,lives:null,invincibleRemaining:null,
            objects:s.objects.filter(o=>o.type!=='obstacle')});
          for(const phase of ['ground','ascending','descending','platform','landing'])for(const hz of [60,120]){
            const s=m.createRunnerState([{at:0,type:'star',height:120},
              {at:.03,type:'platform'}]);s.mode='running';s.score=20;
            if(phase==='ascending'||phase==='descending'){
              m.startJump(s);m.updateRunner(s,phase==='ascending'?.02:.88);
            }
            if(phase==='platform'||phase==='landing'){
              s.objects.push({id:'support',type:'platform',x:186,height:20});
              s.feetY=phase==='platform'?450:449.5;s.velocityY=phase==='platform'?0:100;
              s.supportId=phase==='platform'?'support':null;s.airAction=phase==='platform'?null:'jump';
            }
            const control=structuredClone(s);
            m.updateRunner(control,1/hz);
            const height=m.GROUND_Y-control.feetY+m.characterBob(control);
            // 同じサブステップにスターと複数の岩が接触する。
            s.objects.push({id:'earned-now',type:'star',x:186,height},
              {id:'future-star',type:'star',x:800,height:0});
            const expected=structuredClone(s);
            s.objects.push({id:'rock-a',type:'obstacle',x:186},
              {id:'rock-b',type:'obstacle',x:186});
            m.updateRunner(expected,1/hz);m.updateRunner(s,1/hz);
            const after={mode:s.mode,lives:s.lives,score:s.score,support:s.supportId,
              airAction:s.airAction,shield:s.invincibleRemaining,preserved:checkpoint(s)===checkpoint(expected),
              uncollected:s.objects.some(o=>o.id==='future-star'),
              collected:!s.objects.some(o=>o.id==='earned-now'),nextSpawn:s.nextSpawn};
            const score=s.score;m.updateRunner(s,0);
            after.noDuplicate=s.score===score;results.push({phase,hz,...after});
          }
          return results;
        }""")
        for row in outcomes:
            with self.subTest(phase=row['phase'], hz=row['hz']):
                self.assertEqual((row['mode'],row['lives'],row['score']), ('running',1,30))
                self.assertAlmostEqual(row['shield'], 1-(1/row['hz']-1/120), delta=1e-9)
                self.assertTrue(row['preserved'] and row['uncollected'] and row['collected'] and row['noDuplicate'])
                self.assertGreater(row['nextSpawn'], 0)
                if row['phase'] in ('platform','landing'):
                    self.assertEqual(row['support'], 'support')
                if row['phase'] in ('ascending','descending'):
                    self.assertIsNone(row['support'])
                    self.assertEqual(row['airAction'], 'jump')
        self.assert_isolated(page, errors, requests)

    def test_states_copy_course_without_mutating_stage_or_other_plays(self):
        page, errors, requests = self.stage_runner()
        actual = page.evaluate("""() => {
          const m=runnerModel,before=JSON.stringify(runnerStages);
          return runnerStages.map(stage=>{
            const a=m.createRunnerState(stage),b=m.createRunnerState(stage),fresh=JSON.stringify(b);
            a.course[0].height=999;a.course.reverse();a.mode='running';m.updateRunner(a,1);
            return {id:b.stageId,goalDistance:b.goalDistance,ready:b.mode,
              distinct:a.course!==b.course&&a.course[0]!==b.course[0],
              otherUnchanged:fresh===JSON.stringify(b),definitionUnchanged:before===JSON.stringify(runnerStages)};
          });
        }""")
        for item in actual:
            with self.subTest(stage=item['id']):
                self.assertEqual(item['goalDistance'], EXPECTED[item['id']]['length'])
                self.assertEqual(item['ready'], 'ready')
                self.assertTrue(item['distinct'])
                self.assertTrue(item['otherUnchanged'])
                self.assertTrue(item['definitionUnchanged'])
        self.assert_isolated(page, errors, requests)

    def test_real_frames_and_taps_score_100_on_every_stage_at_60_and_120_hz(self):
        model, model_errors, model_requests = self.stage_runner()
        stages = model.evaluate('runnerStages')
        self.assert_isolated(model, model_errors, model_requests)
        for index, stage in enumerate(stages):
            for hz in (60, 120):
                with self.subTest(stage=stage['stageId'], hz=hz):
                    page, errors, requests = self.manual_runner(course=stage)
                    self.toggle(page)
                    page.evaluate('runnerClock.step(0)')
                    now = 0
                    for seconds in SOLUTIONS[stage['stageId']]['perfect']:
                        target = seconds * 1000
                        page.evaluate('args=>runnerClock.advance(...args)', [target - now, hz])
                        self.tap(page)
                        now = target
                    page.evaluate('args=>runnerClock.advance(...args)',
                                  [stage['goalDistance'] / 200 * 1000 - now, hz])
                    finished = self.snapshot(page)
                    self.assertEqual((finished['score'], finished['progress'], finished['pending']),
                                     (100, 100, 0))
                    self.assertIsNotNone(finished['goal'])
                    self.assertEqual(finished['sprite']['pose'], 'idle')
                    self.assertEqual(page.locator('#runner-result-title').inner_text(), 'クリア！')
                    self.assertEqual(page.locator('#runner-result-score').inner_text(), '100')
                    self.assertEqual(page.locator('#runner-result-progress').inner_text(), '100')
                    self.assertEqual(page.evaluate('runnerClock.advance(10000)'), 0)
                    self.assertEqual(self.snapshot(page)['image'], finished['image'])
                    # ステージ固有のゴール後も、既存の縦横レイアウトを使える。
                    width, height = ((844, 390), (768, 1024), (1024, 768))[index % 3]
                    page.set_viewport_size({'width': width, 'height': height})
                    page.evaluate('runnerClock.settle()')
                    page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                    self.assert_geometry(page)
                    self.assertEqual(self.snapshot(page)['pending'], 0)
                    self.assertTrue(page.locator('#runner-result').is_visible())
                    self.assert_isolated(page, errors, requests)
                    page.context.close()

    def test_real_controls_pause_resume_and_retry_keep_selected_stage(self):
        model, model_errors, model_requests = self.stage_runner()
        stages = model.evaluate('runnerStages')
        self.assert_isolated(model, model_errors, model_requests)
        for stage in stages:
            with self.subTest(stage=stage['stageId']):
                page, errors, requests = self.manual_runner(probe=True, course=stage)
                self.toggle(page);page.evaluate('runnerClock.step(0)')
                page.evaluate('runnerClock.advance(2000,60)')
                self.tap(page)
                page.evaluate('runnerClock.advance(225,60)')
                self.toggle(page)
                paused = page.evaluate('JSON.stringify(runnerJumpProbe.state)')
                self.assertEqual(self.snapshot(page)['pending'], 0)
                page.evaluate('runnerClock.advance(10000,60)')
                self.assertEqual(page.evaluate('JSON.stringify(runnerJumpProbe.state)'), paused)
                self.toggle(page)
                page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                # 新しい2連岩は2回目の接触が早い。第1接触のフレームで止める。
                page.evaluate("""() => {
                  for(let f=0;f<60*60&&runnerJumpProbe.state.lives===2;f++)
                    runnerClock.advance(1000/60,60);
                }""")
                self.assertEqual(page.locator('#runner-toggle').inner_text(), '一時停止')
                self.assertEqual(self.snapshot(page)['pending'], 1)
                first = page.evaluate('JSON.parse(JSON.stringify(runnerJumpProbe.state))')
                self.assertEqual((first['mode'], first['lives']), ('running', 1))
                self.assertEqual(page.locator('#runner-hearts').inner_text(), '♥♡')
                page.evaluate("""() => {
                  for(let f=0;f<60*60&&runnerJumpProbe.state.mode==='running';f++)
                    runnerClock.advance(1000/60,60);
                }""")
                self.assertEqual(page.locator('#runner-result-title').inner_text(), 'ゲームオーバー')
                self.assertEqual(page.evaluate('runnerJumpProbe.state.lives'), 0)
                self.assertEqual(self.snapshot(page)['pending'], 0)
                self.toggle(page)
                page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
                self.tap(page)
                fresh = page.evaluate("""() => {
                  const s=runnerJumpProbe.state;
                  return {id:s.stageId,goalDistance:s.goalDistance,distance:s.distance,
                    elapsed:s.elapsed,score:s.score,feet:s.feetY,origin:s.jumpOriginY,
                    lives:s.lives,invincibleRemaining:s.invincibleRemaining};
                }""")
                self.assertEqual(fresh, {'id': stage['stageId'], 'goalDistance': stage['goalDistance'],
                    'distance': 0, 'elapsed': 0, 'score': 0, 'feet': 470, 'origin': 470,
                    'lives': 2, 'invincibleRemaining': 0})
                self.assertEqual((self.snapshot(page)['score'], self.snapshot(page)['progress']), (0, 0))
                self.assertTrue(page.locator('#runner-result').is_hidden())
                self.assert_isolated(page, errors, requests)
                page.context.close()


if __name__ == '__main__':
    unittest.main()
