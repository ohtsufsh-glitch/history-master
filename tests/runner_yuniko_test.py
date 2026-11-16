"""Issue #89: 秘密キャラ内部能力・実入力攻略・公開入口の分離。"""
import unittest

import runner_canvas_test as canvas
import runner_preview_test as preview
from runner_difficulty_cases import DESIGN, character_inputs
from runner_difficulty_test import TRIAL


class RunnerYunikoTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    assert_isolated = canvas.RunnerCanvasTest.assert_isolated
    open_runner = canvas.RunnerCanvasTest.open_runner
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    model_runner = canvas.RunnerCanvasTest.model_runner
    preview_runner = preview.RunnerPreviewTest.preview_runner
    settle = preview.RunnerPreviewTest.settle
    state = preview.RunnerPreviewTest.state
    assert_hearts = preview.RunnerPreviewTest.assert_hearts

    def test_air_jump_budget_landing_and_normal_characters(self):
        page, errors, _ = self.model_runner()
        result = page.evaluate("""()=>{
          const m=runnerModel, rows=[];
          for(const id of [...m.CHARACTERS.map(c=>c.characterId),'secret_yuniko']) {
            const s=m.createRunnerState([],id);s.mode='running';
            const first=m.startJump(s);m.updateRunner(s,.6);
            const before=s.feetY,second=m.startJump(s),velocity=s.velocityY;
            const snap=JSON.stringify(s),third=m.startJump(s),unchanged=snap===JSON.stringify(s);
            m.updateRunner(s,2);
            const restored=s.airJumpsRemaining;
            const ground=m.startJump(s);m.updateRunner(s,.2);const again=m.startJump(s);
            rows.push({id,first,second,third,unchanged,velocity,before,restored,ground,again,
              speed:s.speed,jump:s.jump,lives:s.lives});
          }return rows;
        }""")
        for r in result:
            secret = r['id'] == 'secret_yuniko'
            self.assertTrue(r['first'] and r['ground'] and r['unchanged'])
            self.assertFalse(r['third'])
            self.assertEqual((r['second'], r['again'], r['restored']), (secret, secret, int(secret)))
            if secret:
                self.assertLess(r['velocity'], 0)
                self.assertEqual((r['speed'], r['jump']['height'], r['jump']['duration'], r['lives']), (200,120,.9,3))
        self.assertEqual(errors, [])

    def test_platform_landing_restores_and_edge_fall_keeps_one_jump(self):
        page, errors, _ = self.model_runner()
        rows = page.evaluate("""()=>{
          const m=runnerModel,rows=[];
          for(const hz of [60,120]){
            const s=m.createRunnerState([],'secret_yuniko');s.mode='running';
            // 実ジャンプで長い足場へ上から着地する。
            s.objects=[{id:'p',type:'platform',x:300,width:600,height:80}];
            m.startJump(s);m.updateRunner(s,.2);m.startJump(s);
            for(let i=0;i<hz*2&&s.supportId===null;i++)m.updateRunner(s,1/hz);
            const landing={support:s.supportId,budget:s.airJumpsRemaining,feet:s.feetY};
            while(s.supportId!==null)m.updateRunner(s,1/hz);
            const fall={action:s.airAction,budget:s.airJumpsRemaining,feet:s.feetY};
            const jump=m.startJump(s),velocity=s.velocityY,third=m.startJump(s);
            rows.push({hz,landing,fall,jump,velocity,third});
          }return rows;
        }""")
        for r in rows:
            self.assertEqual(r['landing'], dict(support='p',budget=1,feet=390))
            self.assertEqual((r['fall']['action'], r['fall']['budget']), ('fall',1))
            self.assertTrue(r['jump'])
            self.assertLess(r['velocity'],0)
            self.assertFalse(r['third'])
        self.assertEqual(errors, [])

    def test_six_stages_perfect_with_and_without_air_jump_at_both_rates(self):
        page, errors, _ = self.model_runner()
        page.evaluate('() => { window.yunikoTrial = (' + TRIAL + '); }')
        plans = {key: character_inputs(key) for key in DESIGN}
        rows = page.evaluate("""async plans=>{
          const stages=(await import('./stages.js')).STAGES, rows=[];
          for(const stage of stages)for(const hz of [60,120])for(const air of [false,true]){
            // コース通過後の空き区間で通常→空中ジャンプを追加。位置等の補正なし。
            const inputs=[...plans[stage.stageId]];
            if(air)inputs.push(stage.goalDistance/200-1,stage.goalDistance/200-.75);
            const r=yunikoTrial({...stage,characterId:'secret_yuniko',hz,inputs:inputs.sort((a,b)=>a-b)});
            rows.push({stage:stage.stageId,hz,air,...r});
          }return rows;
        }""", plans)
        self.assertEqual(len(rows),24)
        for r in rows:
            with self.subTest(stage=r['stage'],hz=r['hz'],air=r['air']):
                self.assertTrue(r['ok'], r)
                self.assertEqual((r['score'],r['hits'],r['maxShield']), (100,0,0))
                self.assertEqual(sum(j['support'] is None for j in r['jumps']), int(r['air']))
        self.assertEqual(errors, [])

    def test_air_jump_crosses_wall_rock_and_collects_high_star(self):
        page, errors, _ = self.model_runner()
        page.evaluate('() => { window.yunikoTrial = (' + TRIAL + '); }')
        rows = page.evaluate("""()=>{
          const course=[{type:'wall',at:4.89,width:40,height:180},
            {type:'obstacle',at:4.89},{type:'star',at:4.89,height:200}];
          return [60,120].map(hz=>({hz,
            air:yunikoTrial({course,goalDistance:2400,characterId:'secret_yuniko',inputs:[8.1,8.55],hz}),
            single:yunikoTrial({course,goalDistance:2400,characterId:'secret_yuniko',inputs:[8.1],hz})}));
        }""")
        for row in rows:
            self.assertTrue(row['air']['ok'], row)
            self.assertEqual((row['air']['score'],row['air']['hits']), (10,0))
            self.assertIsNone(row['air']['jumps'][1]['support'])
            self.assertGreater(row['single']['hits'],0)
        self.assertEqual(errors, [])

    def test_public_ui_rejects_secret_injected_option_and_url(self):
        for suffix in ('?characterId=secret_yuniko', '?stagePreview=1&characterId=secret_yuniko'):
            page, errors, requests = self.preview_runner(suffix)
            self.assertEqual(self.state(page)['characterId'],'shiba')
            self.assertNotIn('ゆにこ',page.locator('body').inner_text())
            self.assertEqual(page.locator('[src*="secret_yuniko"], option[value="secret_yuniko"]').count(),0)
            page.locator('#runner-character-select').evaluate("""s=>{
              s.add(new Option('injected','secret_yuniko'));s.value='secret_yuniko';
              s.dispatchEvent(new Event('change',{bubbles:true}));
            }""")
            self.assertEqual(self.state(page)['characterId'],'shiba')
            self.assertEqual(page.locator('#runner-character-select').input_value(), 'shiba' if 'stagePreview=1' in suffix else '')
            self.assertFalse(any('secret_yuniko.webp' in url for url in requests))
            self.assertEqual(errors, [])

    def test_isolated_ui_taps_damage_freeze_gameover_and_retry(self):
        page, _, _ = self.preview_runner()
        # 隔離テストだけで初期キャラを差し替える。本番入口・URL・所持データは追加しない。
        source = (canvas.ROOT / 'runner/game.js').read_text()
        source = source.replace('createRunnerState(STAGES[0])', 'createRunnerState(STAGES[0],"secret_yuniko")')
        source = source.replace('function updateControls() {', 'function updateControls() { window.runnerPreviewState = state;')
        page.route('**/runner/game.js*', lambda route: route.fulfill(status=200,content_type='text/javascript',body=source))
        errors=[]
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.reload()
        page.wait_for_function('runnerPreviewState.characterId==="secret_yuniko" && runnerImages.every(i=>i.complete)')
        self.settle(page)
        self.assert_hearts(page,3,3)
        self.assertGreater(page.locator('#runner-character-image').evaluate('i=>i.naturalWidth'),0)
        page.locator('#runner-toggle').tap();page.evaluate('runnerClock.step(0)')
        page.locator('#runner-jump').tap();page.evaluate('runnerClock.advance(200,120)')
        page.locator('#runner-canvas').tap()
        self.assertEqual(self.state(page)['airJumpsRemaining'],0)
        velocity=self.state(page)['velocityY']
        self.assertLess(velocity,0)
        page.locator('#runner-jump').tap()
        self.assertEqual(self.state(page)['velocityY'],velocity)
        # 空中被弾・連続衝突・スター・壁上面を足場扱いしないこと。
        hit=page.evaluate("""()=>{
          const s=runnerPreviewState;
          s.objects=[{id:'wall',type:'wall',x:186,width:100,height:400},
            {id:'star',type:'star',x:186,height:470-43-(s.feetY-43)}];
          runnerClock.advance(1000/120,120);return structuredClone(s);
        }""")
        self.assertEqual((hit['lives'],hit['mode'],hit['airJumpsRemaining'],hit['supportId']), (2,'running',0,None))
        self.assertEqual(hit['score'],10)
        self.assertGreater(hit['hitFeedbackRemaining'],.22)
        self.assertGreater(hit['invincibleRemaining'],.98)
        self.assert_hearts(page,2,3)
        page.locator('#runner-toggle').tap()
        frozen=self.state(page)
        page.evaluate("""()=>{
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));runnerClock.advance(5000,120);
        }""")
        self.assertEqual(self.state(page),frozen)
        page.evaluate("""()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));}""")
        self.settle(page)
        page.locator('#runner-toggle').tap();page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        page.evaluate('runnerClock.advance(50,120)')
        self.assertEqual(self.state(page)['lives'],2)
        page.evaluate('runnerClock.advance(60000,120)')
        self.assertEqual((self.state(page)['reason'],self.state(page)['lives']),('collision',0))
        self.assert_hearts(page,0,3)
        page.locator('#runner-toggle').tap();page.evaluate('runnerClock.step(runnerClock.snapshot().now)')
        s=self.state(page)
        self.assertEqual((s['characterId'],s['lives'],s['airJumpsRemaining'],s['score'],s['distance']), ('secret_yuniko',3,1,0,0))
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
