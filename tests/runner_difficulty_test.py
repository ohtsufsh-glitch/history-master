"""Issue #84: 足場の必要性、入力猶予、壁の実体、60/120Hzの同一挙動。"""

import json
import unittest

import runner_canvas_test as canvas
from runner_difficulty_cases import DESIGN, character_inputs


# 配信される実物理だけを呼ぶ。開始とジャンプ以外で状態を書き換えない。
TRIAL = """({course,goalDistance,characterId,inputs,hz})=>{
  const m=runnerModel,s=m.createRunnerState({course,goalDistance},characterId);
  s.mode='running';let next=0,hits=0,maxShield=0;const jumps=[],landings=new Set();
  for(let f=0;f<hz*(goalDistance/s.speed+2)&&s.mode==='running';f++){
    if(next<inputs.length&&f/hz+1e-9>=inputs[next]){
      const support=s.supportId;
      jumps.push({support,accepted:m.startJump(s),distance:s.distance});next++;
    }
    const lives=s.lives;m.updateRunner(s,1/hz);hits+=lives-s.lives;
    maxShield=Math.max(maxShield,s.invincibleRemaining);
    if(s.supportId!==null&&s.supportId!=='ground')landings.add(s.supportId);
  }
  return {ok:s.reason==='clear'&&hits===0&&next===inputs.length&&jumps.every(j=>j.accepted),
    score:s.score,hits,maxShield,jumps,landings:landings.size};
}"""


class RunnerDifficultyTest(unittest.TestCase):
    setUpClass = classmethod(canvas.RunnerCanvasTest.setUpClass.__func__)
    tearDownClass = classmethod(canvas.RunnerCanvasTest.tearDownClass.__func__)
    open_runner = canvas.RunnerCanvasTest.open_runner
    manual_runner = canvas.RunnerCanvasTest.manual_runner
    model_runner = canvas.RunnerCanvasTest.model_runner
    assert_geometry = canvas.RunnerCanvasTest.assert_geometry
    assert_isolated = canvas.RunnerCanvasTest.assert_isolated

    def difficulty_runner(self):
        page, errors, requests = self.model_runner()
        page.evaluate('() => { window.difficultyTrial = (' + TRIAL + '); }')
        page.evaluate("""async()=>{
          window.runnerStages=(await import('./stages.js')).LEGACY_STAGES;
          // 実ステージから区間を抜き出し、平行移動するだけ。寸法や物理は変えない。
          window.modules=[
            {id:'double',stage:'S02',low:2500,high:3000,shift:1000,goal:2300,score:20},
            {id:'pair',stage:'S03',low:2400,high:3000,shift:1000,goal:2350,score:20},
            {id:'wall',stage:'S04',low:2600,high:3100,shift:1200,goal:2300,score:20},
            {id:'chain',stage:'S06',low:4800,high:5600,shift:3400,goal:2600,score:20},
          ].map(d=>({...d,course:runnerStages.find(s=>s.stageId===d.stage).course
            .filter(e=>e.at*200+822>=d.low&&e.at*200+822<=d.high)
            .map(e=>({...e,at:e.at-d.shift/200}))}));
          window.moduleInputs=(id,c)=>id==='double'?[1600/c.speed-c.jump.duration/2,
              1860/c.speed-c.jump.duration/2]:
            (id==='pair'?[1420,1775]:id==='wall'?[1420,1748]:[1420,1670,2048])
              .map(x=>x/c.speed);
        }""")
        return page, errors, requests

    def test_compound_routes_require_platform_jumps_and_ground_routes_fail(self):
        page, errors, requests = self.difficulty_runner()
        rows = page.evaluate("""()=>{
          const results=[];
          for(const c of runnerModel.CHARACTERS)for(const hz of [60,120])for(const d of modules){
            const args={course:d.course,goalDistance:d.goal,characterId:c.characterId,hz};
            const inputs=moduleInputs(d.id,c),good=difficultyTrial({...args,inputs});
            // 2連は次の入力なし、他は足場からの最後のジャンプなし。
            const walk=difficultyTrial({...args,inputs:inputs.slice(0,-1)});
            const early=difficultyTrial({...args,inputs:inputs.map((t,i)=>i===inputs.length-1?t-.4:t)});
            const late=difficultyTrial({...args,inputs:inputs.map((t,i)=>i===inputs.length-1?t+.4:t)});
            let groundSuccesses=0,groundTrials=0;
            if(d.id==='pair'||d.id==='wall'){
              const course=d.course.filter(e=>e.type!=='platform');
              // 危険の手前から通過後まで、全フレームを開始時刻として探索。
              for(let f=Math.floor(1450/c.speed*hz);f<=Math.ceil(1950/c.speed*hz);f++){
                groundTrials++;
                if(difficultyTrial({...args,course,inputs:[f/hz]}).ok)groundSuccesses++;
              }
            }
            results.push({id:c.characterId,hz,module:d.id,good,walk,early,late,groundTrials,groundSuccesses});
          }
          return results;
        }""")
        for row in rows:
            with self.subTest(character=row['id'], hz=row['hz'], module=row['module']):
                self.assertTrue(row['good']['ok'], row)
                self.assertEqual((row['good']['score'],row['good']['hits'],row['good']['maxShield']), (20,0,0))
                if row['module'] != 'double':
                    self.assertNotIn(row['good']['jumps'][-1]['support'], (None, 'ground'))
                    self.assertGreaterEqual(row['good']['landings'], 2 if row['module']=='chain' else 1)
                for kind in ('walk', 'early', 'late'):
                    self.assertFalse(row[kind]['ok'], (kind,row))
                    self.assertGreater(row[kind]['hits'], 0, (kind,row))
                if row['module'] in ('pair','wall'):
                    self.assertGreater(row['groundTrials'], 100)
                    self.assertEqual(row['groundSuccesses'], 0)
        self.assert_isolated(page, errors, requests)

    def test_perfect_route_has_contiguous_human_input_windows_at_both_rates(self):
        page, errors, requests = self.difficulty_runner()
        rows = page.evaluate("""()=>{
          const results=[];
          for(const c of runnerModel.CHARACTERS)for(const hz of [60,120])for(const d of modules){
            const inputs=moduleInputs(d.id,c);
            for(let action=0;action<inputs.length;action++){
              let streak=0,best=0,start=null,bestRange=null;
              for(let offset=-Math.floor(hz*.4);offset<=Math.floor(hz*.4);offset++){
                const candidate=inputs.map((t,i)=>t+(i===action?offset/hz:0));
                const r=difficultyTrial({course:d.course,goalDistance:d.goal,
                  characterId:c.characterId,inputs:candidate,hz});
                if(r.ok&&r.score===d.score){
                  if(streak===0)start=offset/hz;
                  streak++;
                  if(streak>best){best=streak;bestRange=[start,offset/hz];}
                }else streak=0;
              }
              results.push({id:c.characterId,hz,module:d.id,action,range:bestRange,
                width:(best-1)/hz});
            }
          }
          return results;
        }""")
        for row in rows:
            with self.subTest(**{k:row[k] for k in ('id','hz','module','action')}):
                self.assertGreaterEqual(row['width']+1e-9, .15, row)
        # 検証資料へ転記する実測結果。単一の成功フレームだけで判定しない。
        print('DIFFICULTY_INPUT_WINDOWS=' + json.dumps(rows, ensure_ascii=False))
        self.assert_isolated(page, errors, requests)

    def test_all_character_stage_motion_traces_match_60_and_120_hz(self):
        page, errors, requests = self.difficulty_runner()
        plans = {c: {key: character_inputs(key,speed,duration) for key in DESIGN}
                 for c,speed,duration in [('shiba',200,.9),('sloth',170,1.1),
                                          ('goldfish',185,1.05),('salamander',230,.82)]}
        rows = page.evaluate("""plans=>{
          const m=runnerModel,results=[];
          for(const c of m.CHARACTERS)for(const stage of runnerStages){
            // 同じ時刻の入力を与え、同じ実時間の全フレーム状態を比較。
            const inputs=plans[c.characterId][stage.stageId].map(t=>Math.ceil(t*60-1e-9)/60);
            function trace(hz){
              const s=m.createRunnerState(stage,c.characterId);s.mode='running';let next=0;
              const rows=[];
              for(let f=0;f<hz*60&&s.mode==='running';f++){
                if(next<inputs.length&&f/hz+1e-9>=inputs[next]){m.startJump(s);next++;}
                m.updateRunner(s,1/hz);
                if((f+1)%(hz/60)===0||s.mode!=='running')rows.push({
                  feet:s.feetY,velocity:s.velocityY,distance:s.distance,elapsed:s.elapsed,
                  support:s.supportId,origin:s.jumpOriginY,pose:m.characterPose(s),
                  score:s.score,lives:s.lives,shield:s.invincibleRemaining,mode:s.mode,
                  objects:s.objects.map(o=>({id:o.id,x:o.x}))});
              }
              return rows;
            }
            const a=trace(60),b=trace(120);let maxError=0,discreteEqual=a.length===b.length;
            for(let i=0;i<Math.min(a.length,b.length);i++){
              for(const key of ['feet','velocity','distance','elapsed','origin','shield'])
                maxError=Math.max(maxError,Math.abs(a[i][key]-b[i][key]));
              for(const key of ['support','pose','score','lives','mode'])
                discreteEqual&&=a[i][key]===b[i][key];
              discreteEqual&&=a[i].objects.length===b[i].objects.length;
              for(let j=0;j<Math.min(a[i].objects.length,b[i].objects.length);j++){
                discreteEqual&&=a[i].objects[j].id===b[i].objects[j].id;
                maxError=Math.max(maxError,Math.abs(a[i].objects[j].x-b[i].objects[j].x));
              }
            }
            results.push({id:c.characterId,stage:stage.stageId,maxError,discreteEqual,
              end:a.at(-1),initialLives:c.initialLives});
          }
          return results;
        }""", plans)
        self.assertEqual(len(rows), 24)
        for row in rows:
            with self.subTest(character=row['id'], stage=row['stage']):
                self.assertLess(row['maxError'], 1e-6, row)
                self.assertTrue(row['discreteEqual'], row)
                self.assertEqual((row['end']['mode'],row['end']['score'],row['end']['lives'],row['end']['shield']),
                                 ('finished',100,row['initialLives'],0))
        self.assert_isolated(page, errors, requests)

    def test_wall_rectangle_contacts_size_culling_and_no_landing(self):
        page, errors, requests = self.difficulty_runner()
        rows = page.evaluate("""()=>{
          const m=runnerModel,results=[];
          for(const c of m.CHARACTERS)for(const hz of [60,120]){
            function contact(x,feet){
              const s=m.createRunnerState([],c.characterId);s.mode='running';
              s.supportId=null;s.feetY=feet;
              s.objects=[{id:'wall',type:'wall',x,width:96,height:210}];
              m.updateRunner(s,0);return {hits:s.initialLives-s.lives,support:s.supportId};
            }
            const s=m.createRunnerState([],c.characterId);s.mode='running';
            s.supportId=null;s.feetY=258;s.velocityY=100;
            s.objects=[{id:'wall',type:'wall',x:186,width:96,height:210}];
            m.updateRunner(s,1/hz);
            const removed=[];
            for(const x of [-99.99,-100.01]){
              const state=m.createRunnerState([],c.characterId);state.mode='running';
              state.objects=[{id:'wide',type:'wall',x,width:200,height:210}];
              m.updateRunner(state,0);removed.push(state.objects.length);
            }
            results.push({id:c.characterId,hz,
              bounds:m.wallBounds({x:186,width:96,height:210}),
              sideOutside:contact(186+48+28+.01,350),sideTouch:contact(186+48+28,350),
              topOutside:contact(186,274.99),topTouch:contact(186,275),
              aboveRock:contact(186,350),removed,
              falling:{support:s.supportId,lives:s.lives,feet:s.feetY}});
          }
          return results;
        }""")
        for row in rows:
            with self.subTest(character=row['id'], hz=row['hz']):
                self.assertEqual(row['bounds'], dict(left=138,right=234,top=260,bottom=470,width=96,height=210))
                for kind in ('sideOutside', 'topOutside'):
                    self.assertEqual(row[kind]['hits'], 0)
                for kind in ('sideTouch', 'topTouch', 'aboveRock'):
                    self.assertEqual(row[kind]['hits'], 1)
                self.assertEqual(row['removed'], [1,0])
                self.assertIsNone(row['falling']['support'])
                self.assertGreater(row['falling']['feet'], 258)
        self.assert_isolated(page, errors, requests)

    def test_wall_shield_auto_continue_and_fatal_goal_priority(self):
        page, errors, requests = self.difficulty_runner()
        rows = page.evaluate("""()=>{
          const m=runnerModel,results=[];
          for(const c of m.CHARACTERS)for(const hz of [60,120]){
            const s=m.createRunnerState([],c.characterId);s.mode='running';
            s.objects=[{id:'w1',type:'wall',x:186,width:100,height:180},
              {id:'w2',type:'wall',x:186,width:100,height:220},
              {id:'r',type:'obstacle',x:186},{id:'star',type:'star',x:186,height:0}];
            m.updateRunner(s,1/hz);
            const first={lives:s.lives,score:s.score,mode:s.mode,distance:s.distance,shield:s.invincibleRemaining};
            s.mode='paused';const paused=JSON.stringify(s);m.updateRunner(s,10);
            const pauseStable=paused===JSON.stringify(s);m.resumeRunner(s);
            for(let f=1;f<hz;f++){
              for(const o of s.objects)if(o.type!=='star')o.x=186;
              m.updateRunner(s,1/hz);
            }
            const protectedLives=s.lives;
            for(const o of s.objects)if(o.type!=='star')o.x=186;
            m.updateRunner(s,2/hz);
            const after=s.lives;
            const goals=[];
            for(const lives of [1,2]){
              const g=m.createRunnerState({goalDistance:1000,course:[]},c.characterId);
              g.mode='running';g.lives=lives;g.distance=999;
              g.objects=[{id:'wall',type:'wall',x:186,width:40,height:180},
                {id:'star',type:'star',x:186,height:0}];
              m.updateRunner(g,1/hz);
              goals.push({mode:g.mode,reason:g.reason,lives:g.lives,score:g.score});
            }
            results.push({id:c.characterId,hz,initial:c.initialLives,first,pauseStable,protectedLives,after,goals});
          }
          return results;
        }""")
        for row in rows:
            with self.subTest(character=row['id'], hz=row['hz']):
                self.assertEqual((row['first']['lives'],row['first']['score'],row['first']['mode']),
                                 (row['initial']-1,10,'running'))
                self.assertGreater(row['first']['distance'], 0)
                self.assertGreaterEqual(row['first']['shield'],1-1/row['hz'])
                self.assertTrue(row['pauseStable'])
                self.assertEqual(row['protectedLives'],row['initial']-1)
                self.assertEqual(row['after'],row['initial']-2)
                self.assertEqual(row['goals'], [dict(mode='finished',reason='collision',lives=0,score=0),
                                               dict(mode='finished',reason='clear',lives=1,score=10)])
        self.assert_isolated(page, errors, requests)

    def test_wall_canvas_matches_bounds_at_phone_tablet_sizes_without_images(self):
        # 描画関数だけをテスト用module経由で取得。本番の公開APIは増やさない。
        page, errors, requests = self.model_runner()
        source = (canvas.ROOT / 'runner/game.js').read_text()
        source = source.replace('initializeRunner();', '') + '\nexport { drawObjects };'
        page.route('**/runner/wall-render-test.js', lambda route: route.fulfill(
            status=200,content_type='text/javascript',body=source))
        page.evaluate("""async()=>{
          window.wallRenderer=await import('./wall-render-test.js');
          window.wallPaints=[];
          const p=CanvasRenderingContext2D.prototype,fill=p.fillRect;
          p.fillRect=function(x,y,width,height){
            if(this.fillStyle==='#936247')wallPaints.push({x,y,width,height});
            return fill.call(this,x,y,width,height);
          };
        }""")
        for width,height in [(375,667),(667,375),(768,1024),(1024,768)]:
            page.set_viewport_size(dict(width=width,height=height))
            painted = page.evaluate("""()=>{
              const c=document.querySelector('canvas'),ctx=c.getContext('2d');
              wallPaints.length=0;
              wallRenderer.drawObjects(ctx,{objects:[
                {type:'wall',x:400,width:40,height:180},
                {type:'wall',x:600,width:96,height:220},
                {type:'wall',x:1030,width:160,height:200}]},null);
              return wallPaints;
            }""")
            self.assertEqual(painted,[dict(x=380,y=290,width=40,height=180),
                                      dict(x=552,y=250,width=96,height=220),
                                      dict(x=950,y=270,width=160,height=200)])
        # テストmoduleだけはisolationの同一runnerパスに含まれる。
        self.assert_isolated(page, errors, requests)


if __name__ == '__main__':
    unittest.main()
