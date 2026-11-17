"""Issue #92: 課金の実TX・再開完全性・結果の正本を独立DBで検証。"""
import unittest
import plush_test as plush
from runner_difficulty_cases import SOLUTIONS


class RunnerSessionTest(unittest.TestCase):
    setUpClass = classmethod(plush.PlushTest.setUpClass.__func__)
    tearDownClass = classmethod(plush.PlushTest.tearDownClass.__func__)

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.goto(self.url)
        self.page.wait_for_function('appReady')
        self.page.evaluate(plush.FIXTURE_HELPERS)
        self.page.evaluate("""async()=>{
          window.m=await loadRunnerModel();
          window.install=async(balance=30)=>{
            const d=plushFixture([], 'test');d.coinEvents=[];d.reviewEvents=[];d.coinSpends=[];
            d.arcadePlays=[];d.arcadePrizes=[];
            for(let i=0;i<balance;i++)d.reviewEvents.push({key:'r'+i,profile:'student',amount:1});
            await plushInstall(d);
          };
          window.buy=(extra={})=>purchaseRunnerPlay({profile:'student',stageId:'S01',characterId:'shiba',...extra});
          window.rejected=async f=>{try{await f();return false;}catch{return true;}};
          await install();
        }""")

    def tearDown(self):
        self.context.close()

    def test_balance_boundaries_free_profile_and_repeat(self):
        self.assertEqual(self.page.evaluate("""async()=>{
          const out=[];
          for(const balance of [0,29,30,31]) {
            await install(balance);const ok=!await rejected(()=>buy());
            const d=await snapshotAllStores();out.push([ok,d.runnerPlays.length,d.coinSpends.length]);
          }
          const p=await buy(),again=await buy({id:'other'}),free=await buy({profile:'test'});
          return {out,same:p.id===again.id,free:free.profile,
            spends:(await readAll('coinSpends')).map(s=>s.amount).sort((a,b)=>a-b)};
        }"""),dict(out=[[False,0,0],[False,0,0],[True,1,1],[True,1,1]],same=True,free='test',spends=[0,30]))

    def test_two_tabs_double_tap_and_ufo_spend_serialize(self):
        other=self.context.new_page();other.goto(self.url);other.wait_for_function('appReady')
        self.page.evaluate("window.pending=Promise.all(Array.from({length:5},()=>buy()))")
        other.evaluate("window.pending=purchaseRunnerPlay({profile:'student',stageId:'S01',characterId:'goldfish'})")
        first=self.page.evaluate('async()=> (await pending).map(p=>p.id)')
        second=other.evaluate('async()=> (await pending).id')
        self.assertEqual(set(first+[second]),{first[0]})
        self.assertEqual(self.page.evaluate("async()=>{await install(100);const r=await Promise.allSettled([buy(),purchaseCranePlay(newArcadePlay('student'))]);const d=await snapshotAllStores();return [r.filter(x=>x.status==='fulfilled').length,availableCoins(d.coinEvents,d.reviewEvents,d.coinSpends,'student')>=0,d.coinSpends.length];}"),[1,True,1])

    def test_purchase_rollback_on_sync_and_async_storage_failure(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          for(const asyncFailure of [false,true]) {
            const original=IDBObjectStore.prototype.add;
            IDBObjectStore.prototype.add=function(value){
              if(this.name==='runnerPlays') {
                if(!asyncFailure)throw new DOMException('test','QuotaExceededError');
                original.call(this,value);return original.call(this,value);
              }return original.call(this,value);
            };
            let failed;
            try{failed=await rejected(()=>buy());}finally{IDBObjectStore.prototype.add=original;}
            if(!failed||(await readAll('coinSpends')).length||(await readAll('runnerPlays')).length)return false;
          }return true;
        }"""))

    def test_entitlements_rechecked_and_profiles_isolated(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          if(!await rejected(()=>buy({stageId:'S02'}))||!await rejected(()=>buy({characterId:'secret_yuniko'})))return false;
          await runnerTransaction(['arcadePrizes'],tx=>tx.objectStore('arcadePrizes').put({id:'prize',profile:'test',prizeId:'secret_yuniko'}));
          if(!await rejected(()=>buy({characterId:'secret_yuniko'})))return false;
          const p=await buy({profile:'test',characterId:'secret_yuniko'});
          return p.characterId==='secret_yuniko'&&await rejected(()=>openRunnerSession('student',p.id));
        }"""))

    def test_exact_resume_on_platform_falling_air_jump_stars_shield(self):
        out=self.page.evaluate("""solutions=>{
          const seen=new Set();let samples=0;
          for(const characterId of ['shiba','secret_yuniko'])for(const path of ['perfect','fall','hit']) {
            const s=m.createRunnerState(m.getStage('S03',1),characterId);s.mode='running';let n=0;
            for(let frame=0;frame<1800&&s.mode!=='finished';frame++) {
              const inputs=solutions.S03.perfect;
              if(path==='hit'&&characterId==='secret_yuniko'&&frame===10)m.startJump(s);
              if(path!=='hit'&&n<inputs.length&&frame/60>=inputs[n]){m.startJump(s);n++;}
              if(characterId==='secret_yuniko'&&s.supportId===null&&s.airJumpsRemaining&&s.velocityY>0&&path==='hit')m.startJump(s);
              if(path==='fall'&&s.distance>2600&&s.distance<2800)n=inputs.length;
              m.updateRunner(s,1/60);
              if(s.mode==='finished')break;
              const p={stageId:'S03',characterId,stageVersion:1,score:s.score,snapshot:m.snapshotRunner(s)};
              const r=m.restoreRunner(p);m.resumeRunner(r);
              if(s.supportId!==null&&s.supportId!=='ground')seen.add('platform');
              if(s.airAction==='fall')seen.add('fall');
              if(characterId==='secret_yuniko'&&s.airJumpsRemaining===0)seen.add('airjump');
              if(s.score)seen.add('star');if(s.invincibleRemaining)seen.add('shield');
              m.updateRunner(r,1/60);
              const c=structuredClone(s);m.updateRunner(c,1/60);
              if(JSON.stringify(m.snapshotRunner(c))!==JSON.stringify(m.snapshotRunner(r)))throw new Error('復元後の軌道差異');
              samples++;
            }
          }return {seen:[...seen].sort(),samples};
        }""",SOLUTIONS)
        self.assertEqual(out['seen'],['airjump','fall','platform','shield','star'])
        self.assertGreater(out['samples'],1000)

    def test_save_reload_conflicts_failures_and_legacy_retention(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy();window.s=await openRunnerSession('student',p.id,{lifecycle:false});
          const stale=await openRunnerSession('student',p.id,{lifecycle:false});
          await s.resume();await s.advance(.25);await s.pause();
          if(!await rejected(()=>stale.resume()))return false;
          const resumed=await openRunnerSession('student',p.id,{lifecycle:false});
          if(resumed.view.state.distance!==s.view.state.distance)return false;
          const original=IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put=function(v){if(this.name==='runnerPlays')throw new Error('disk full');return original.call(this,v);};
          try{if(!await rejected(()=>resumed.resume())||!resumed.view.dirty||!resumed.view.error)return false;}
          finally{IDBObjectStore.prototype.put=original;}
          const d=await readAll('runnerPlays');d[0].stageVersion=99;
          await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').put(d[0]));
          if((await buy()).id!==p.id||!await rejected(()=>openRunnerSession('student',p.id)))return false;
          return (await readAll('coinSpends')).length===1;
        }"""))
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertEqual(self.page.evaluate("async()=>[(await readAll('coinSpends')).length,(await readAll('runnerPlays'))[0].stageVersion]"),[1,99])

    def test_lifecycle_hide_pauses_and_commits_without_finishing(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy();const c=await openRunnerSession('student',p.id);
          const starting=c.resume();window.dispatchEvent(new Event('pagehide'));await starting.catch(()=>{});
          if(c.view.state.mode!=='paused')return false;
          window.dispatchEvent(new Event('pageshow'));await c.resume();await c.advance(.5);window.dispatchEvent(new Event('pagehide'));
          await c.checkpoint();window.dispatchEvent(new Event('pageshow'));
          return c.view.state.mode==='paused'&&!c.view.dirty&&c.view.savedPlay.status==='active';
        }"""))
        self.page.reload();self.page.wait_for_function('appReady')
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=(await readAll('runnerPlays'))[0];const c=await openRunnerSession('student',p.id,{lifecycle:false});
          return c.view.state.mode==='paused'&&Math.abs(c.view.state.distance-100)<1e-6&&(await readAll('coinSpends')).length===1;
        }"""))

    def test_results_idempotent_retry_unlock_and_gameover_best(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          await install(100);const p=await buy(),s=m.createRunnerState(m.STAGES[0]);
          s.mode='running';while(s.mode!=='finished')m.updateRunner(s,.05);
          const snap=m.snapshotRunner(s);
          const [a,b]=await Promise.all([saveRunnerState('student',p.id,p.updatedAt,snap),saveRunnerState('student',p.id,p.updatedAt,snap)]);
          if(a.result.reason!=='gameover'||a.updatedAt!==b.updatedAt)return false;
          if(summarizeRunnerPlays([a],'student').unlockedStageIds.length!==1)return false;
          const retry=await buy();if(retry.id===p.id)return false;
          const c=m.createRunnerState(m.STAGES[0]);c.mode='running';c.invincibleRemaining=0;
          // ゴール0点は形式上有効な終了状態。実軌道は別の復元試験で検証。
          c.distance=c.goalDistance;c.nextSpawn=c.course.length;c.objects=c.course.map((e,id)=>({...e,id,spawnDistance:e.at*200,x:1008-(c.distance-e.at*200)})).filter(o=>o.x+40>=0);
          c.mode='finished';c.reason='clear';
          const clear=await saveRunnerState('student',retry.id,retry.updatedAt,m.snapshotRunner(c));
          const summary=summarizeRunnerPlays([a,clear],'student');
          return clear.score===0&&summary.unlockedStageIds.includes('S02')&&summary.bestByStage.S01.score===a.score&&(await readAll('coinSpends')).length===2;
        }"""))

    def test_controller_finishes_and_failed_result_preserves_paid_checkpoint(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy(),c=await openRunnerSession('student',p.id,{lifecycle:false});await c.resume();
          while(c.view.state.mode!=='finished')await c.advance(.05);
          if(c.view.dirty||c.view.savedPlay.result.reason!=='gameover')return false;
          await install(30);const next=await buy(),failed=await openRunnerSession('student',next.id,{lifecycle:false});await failed.resume();
          const original=IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put=function(v){if(this.name==='runnerPlays'&&v.status==='finished')throw new Error('disk full');return original.call(this,v);};
          try{while(failed.view.state.mode!=='finished')await failed.advance(.05);}catch{}finally{IDBObjectStore.prototype.put=original;}
          if(!failed.view.error||!failed.view.dirty||failed.view.savedPlay.status!=='active')return false;
          const recovered=await openRunnerSession('student',next.id,{lifecycle:false});
          return recovered.view.state.lives>0&&(await buy()).id===next.id&&(await readAll('coinSpends')).length===1;
        }"""))

    def test_invalid_snapshots_nonterminal_finish_and_100_gameover(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy();
          for(const mutation of [s=>s.nextSpawn++,s=>s.objects.push({id:0}),s=>s.supportId=42,
            s=>s.score=100,s=>s.mode='finished',s=>s.airJumpsRemaining=1,s=>s.extra=true]) {
            const snap=structuredClone(p.snapshot);mutation(snap);
            if(!await rejected(()=>saveRunnerState('student',p.id,p.updatedAt,snap)))return false;
          }
          if(JSON.stringify((await readAll('runnerPlays'))[0])!==JSON.stringify(p))return false;
          const s=m.createRunnerState(m.STAGES[0]);s.mode='running';
          while(s.mode!=='finished')m.updateRunner(s,.05);
          s.collectedStarIds=s.course.map((e,id)=>e.type==='star'?id:null).filter(id=>id!==null);
          s.nextSpawn=s.course.length;s.distance=s.goalDistance;s.objects=[];s.score=100;
          const result=await saveRunnerState('student',p.id,p.updatedAt,m.snapshotRunner(s));
          const summary=summarizeRunnerPlays([result],'student');
          return result.result.reason==='gameover'&&summary.bestByStage.S01.score===100&&summary.unlockedStageIds.length===1;
        }"""))

    def test_v2_backup_roundtrip_and_v1_retained_without_reconstruction(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const p=await buy();const before=await snapshotAllStores();
          // 合成残高は他テスト専用なので、ここでは実fixtureの有効な報酬を使う。
          const valid=plushFixture([], 'test');valid.runnerPlays=before.runnerPlays;valid.coinSpends=before.coinSpends;
          validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:valid});
          await replaceAllStores(valid);const after=await readAll('runnerPlays');
          if(JSON.stringify(after)!==JSON.stringify(before.runnerPlays))return false;
          const old=structuredClone(p);old.snapshot={version:1,distance:100,elapsedSeconds:2,livesRemaining:1,collectedStarIds:[],player:{x:186,y:470,vx:200,vy:0},shieldSeconds:0,airJumpsUsed:0};
          validateRunnerPlays([old]);await runnerTransaction(['runnerPlays'],tx=>tx.objectStore('runnerPlays').put(old));
          return !runnerCanResume(old)&&await rejected(()=>openRunnerSession('student',old.id))&&(await buy()).id===old.id;
        }"""))
