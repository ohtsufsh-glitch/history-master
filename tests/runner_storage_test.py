"""C3-A: 一時ブラウザの独立DBだけを使う保存・互換・ロールバック試験。"""
import json
import subprocess
import plush_test as plush
from plush_test import FIXTURE_HELPERS, ROOT
import unittest


class RunnerStorageTest(unittest.TestCase):
    setUpClass = classmethod(plush.PlushTest.setUpClass.__func__)
    tearDownClass = classmethod(plush.PlushTest.tearDownClass.__func__)

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.goto(self.url)
        self.page.wait_for_function('appReady')
        self.page.evaluate(FIXTURE_HELPERS)
        self.page.evaluate("""()=>{
          window.runnerFixture=()=>{
            const d=plushFixture(['shiba'],'student');
            const at='2020-01-01T00:00:00.000Z';
            window.addRunner=(d,id,profile='student',stageId='S01',characterId='shiba',score=0,status='finished',reason='clear')=>{
              const p={id,profile,game:'runner',schemaVersion:1,stageId,characterId,stageVersion:1,
                startedAt:at,updatedAt:at,status,score};
              if(status==='active')p.snapshot={version:1,distance:100,elapsedSeconds:2,livesRemaining:1,
                collectedStarIds:[0],player:{x:100,y:0,vx:200,vy:0},shieldSeconds:0.5,airJumpsUsed:0};
              else p.result={reason,at,livesRemaining:reason==='clear'?1:0};
              d.runnerPlays.push(p);d.coinSpends.push({id,profile,game:'runner',amount:profile==='test'?0:30,at});return p;
            };
            addRunner(d,'r1');addRunner(d,'r2','student','S01','goldfish',90,'finished','gameover');
            addRunner(d,'r3','student','S02','secret_yuniko',100,'active');
            addRunner(d,'r4','test','S01','secret_yuniko',100);
            return d;
          };
          window.checkRunner=d=>validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:10,data:d});
        }""")

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def test_v9_upgrade_preserves_all_sixteen_stores_and_balance(self):
        old = subprocess.check_output(['git','show','origin/main:index.html'], cwd=ROOT, text=True)
        self.page.evaluate('db.close()')
        # 同一DB名、一時コンテキスト内でのみ旧版DBを作り直す。
        self.page.evaluate("() => new Promise(ok=>{const r=indexedDB.deleteDatabase(DB_NAME);r.onsuccess=ok;})")
        self.page.route(self.url, lambda r: r.fulfill(body=old,content_type='text/html'))
        self.page.reload(); self.page.wait_for_function('appReady')
        self.page.evaluate(FIXTURE_HELPERS)
        self.page.evaluate("async()=>plushInstall(plushFixture(['shiba'],'student'))")
        self.page.evaluate("""async()=>{
          const q=allQuestionRecords().find(q=>q.id==='TEST-PLUSH-001'),at='2020-01-01T00:00:00.000Z';
          await importFeedbackRecords([{questionId:q.id,questionRevision:questionRevision(q),
            questionHash:await sha256Text(questionFingerprintSource(q)),questionSnapshot:{...exportableQuestion(q),deleted:false},
            reporterRole:'learner',sourceProfile:'student',category:'answer',comment:'架空の指摘',createdAt:at,reportId:crypto.randomUUID()}]);
          await navigateHome('student');await startStudy('genre','culture');
        }""")
        self.page.wait_for_function('!studyStarting')
        before=self.page.evaluate('snapshotAllStores()')
        self.assertTrue(all(before.values()), '旧16ストアすべてに架空レコードを用意する')
        balance=self.page.evaluate("async()=>{const d=await snapshotAllStores();return availableCoins(d.coinEvents,d.reviewEvents,d.coinSpends,'student');}")
        self.assertEqual(len(before),16)
        self.page.unroute(self.url);self.page.reload();self.page.wait_for_function('appReady')
        after=self.page.evaluate('snapshotAllStores()')
        self.assertEqual(self.page.evaluate('[db.name,db.version]'),['history-master-sample-v1',10])
        self.assertEqual(after.pop('runnerPlays'),[])
        self.assertEqual(after,before)
        self.assertEqual(self.page.evaluate("async()=>{const d=await snapshotAllStores();return availableCoins(d.coinEvents,d.reviewEvents,d.coinSpends,'student');}"),balance)

    def test_roundtrip_reset_and_rollback(self):
        result=self.page.evaluate("""async()=>{
          const d=checkRunner(runnerFixture());await plushInstall(d);
          const before=await snapshotAllStores();await replaceAllStores(checkRunner(before));
          const same=JSON.stringify(await snapshotAllStores())===JSON.stringify(before);
          // 有効なrunner書込の後で同期DataCloneError、さらに非同期キー制約エラー。
          let rolled=true;
          for(const name of ['runnerPlays','answers']) {
            const bad=structuredClone(before);
            bad[name].push(name==='runnerPlays'?{...d.runnerPlays[0],id:'bad',snapshot:()=>{}}:{id:{}});
            try{await replaceAllStores(bad);rolled=false;}catch{}
            rolled=rolled&&JSON.stringify(await snapshotAllStores())===JSON.stringify(before);
          }
          await performReset({student:true});const reset=await snapshotAllStores();
          checkRunner(reset);
          const kept=reset.runnerPlays.map(p=>p.profile);
          await performReset({test:true});checkRunner(await snapshotAllStores());
          await performReset({},true);const empty=await snapshotAllStores();
          return {same,rolled,kept,empty:Object.values(empty).every(a=>!a.length)};
        }""")
        self.assertEqual(result,dict(same=True,rolled=True,kept=['test'],empty=True))

    def test_legacy_all_versions_and_runner_spend_injection(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          for(let version=1;version<10;version++) {
            const d=plushFixture();delete d.runnerPlays;
            const checked=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:version,data:d});
            if(checked.runnerPlays.length||!runnerRestoreNote(checked).includes('すべて削除'))return false;
            await replaceAllStores(checked);
            if((await readAll('runnerPlays')).length)return false;
            d.coinSpends.push({id:'x',game:'runner',profile:'test',amount:0,at:'x'});
            try{validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:version,data:d});return false;}catch{}
          }return true;
        }"""))

    def test_corrupt_runner_and_payment_records_are_rejected(self):
        mutations=[
            "d.runnerPlays.push(structuredClone(p))", "p.profile='other'", "p.stageId='S07'",
            "p.characterId='unknown'", "p.score=101", "p.score=-1", "p.score=1.2",
            "p.startedAt='yesterday'", "p.updatedAt='2019-01-01T00:00:00.000Z'",
            "p.result.livesRemaining=0", "p.result.reason='quit'", "p.extra=true",
            "d.runnerPlays[2].snapshot.player.x=Infinity", "d.runnerPlays[2].snapshot.collectedStarIds=[1,1]",
            "d.runnerPlays[2].snapshot.airJumpsUsed=2", "d.runnerPlays[2].snapshot.livesRemaining=4",
            "d.runnerPlays[2].snapshot.version=2", "delete d.runnerPlays[2].snapshot.player",
            "p.snapshot={}", "delete p.result", "d.coinSpends.pop()",
            "d.coinSpends.push(structuredClone(d.coinSpends[1]))", "d.coinSpends[1].amount=0",
            "d.coinSpends[1].profile='test'", "d.coinSpends[1].game='crane'", "d.coinSpends[1].at='wrong'",
            "d.coinSpends[4].amount=30", "d.reviewEvents=[]",
            "addRunner(d,'active2','student','S01','shiba',0,'active')",
            "p.id=d.arcadePlays[0].id", "d.runnerPlays=Array(100001).fill(p)"
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertTrue(self.page.evaluate("""mutation=>{
                  const d=runnerFixture(),p=d.runnerPlays[0];eval(mutation);
                  try{checkRunner(d);return false;}catch{return true;}
                }""",mutation))

    def test_derived_scores_unlocks_and_resume_version(self):
        out=self.page.evaluate("""()=>{
          const d=checkRunner(runnerFixture());
          const student=summarizeRunnerPlays(d.runnerPlays,'student'),test=summarizeRunnerPlays(d.runnerPlays,'test');
          const initial=summarizeRunnerPlays([],'student');
          const p=d.runnerPlays[2];p.stageVersion=2;checkRunner(d);
          return {initial:initial.unlockedStageIds,unlocked:student.unlockedStageIds,
            score:student.bestByStage.S01.score,character:student.bestByStage.S01.characterId,
            shiba:student.bestByStageCharacter['S01:shiba'].score,test:test.bestByStage.S01.score,
            resume:runnerCanResume(p),noActive:!student.bestByStage.S02};
        }""")
        self.assertEqual(out,dict(initial=['S01'],unlocked=['S01','S02'],score=90,character='goldfish',shiba=0,test=100,resume=False,noActive=True))

    def test_download_preview_restore_and_legacy_warning_cancel(self):
        accept_dialog=lambda d:d.accept()
        self.page.on('dialog', accept_dialog)
        self.page.evaluate('async()=>plushInstall(checkRunner(runnerFixture()))')
        before=self.page.evaluate('snapshotAllStores()')
        self.page.locator('#open-admin').click()
        self.page.locator('#admin-backup-group > summary').click()
        self.page.locator('#toggle-backup').click()
        with self.page.expect_download() as event:
            self.page.locator('#backup-export').click()
        from pathlib import Path
        backup=json.loads(Path(event.value.path()).read_text())
        self.assertEqual(backup['backupVersion'],10)
        self.assertEqual(backup['data'],before)
        self.page.locator('#backup-file').set_input_files({'name':'synthetic-v10.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
        self.page.wait_for_function("$('backup-preview').textContent.startsWith('検査OK')")
        self.assertIn('ランナー記録：4件',self.page.locator('#backup-preview').inner_text())
        self.page.locator('#backup-restore').click()
        self.page.wait_for_function('!backingUp&&pendingRestore===null')
        self.assertEqual(self.page.evaluate('snapshotAllStores()'),before)
        backup['backupVersion']=9
        backup['data']['coinSpends']=[s for s in before['coinSpends'] if s['game']=='crane']
        del backup['data']['runnerPlays']
        self.page.locator('#backup-file').set_input_files({'name':'synthetic-v9.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
        self.page.wait_for_function("$('backup-preview').textContent.startsWith('検査OK')")
        self.assertIn('すべて削除',self.page.locator('#backup-preview').inner_text())
        self.page.remove_listener('dialog', accept_dialog)
        messages=[]
        self.page.on('dialog',lambda d:(messages.append(d.message),d.dismiss()))
        self.page.locator('#backup-restore').click()
        self.assertIn('すべて削除',messages[0])
        self.assertEqual(self.page.evaluate('snapshotAllStores()'),before)
        self.page.evaluate('async()=>{await replaceAllStores(pendingRestore);}')
        after=self.page.evaluate('snapshotAllStores()')
        self.assertEqual(after['runnerPlays'],[])
        self.assertEqual(after,backup['data'] | {'runnerPlays':[]})

    def test_async_restore_failure_rolls_back_and_other_profile_reset(self):
        self.assertTrue(self.page.evaluate("""async()=>{
          const d=checkRunner(runnerFixture());await plushInstall(d);
          const before=await snapshotAllStores(),put=IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put=function(value,...args){
            const req=put.call(this,value,...args);
            if(this.name==='runnerPlays')this.add(value); // 同じTX内の非同期ConstraintError
            return req;
          };
          let rejected=false;
          try{await replaceAllStores(d);}catch{rejected=true;}
          finally{IDBObjectStore.prototype.put=put;}
          if(!rejected||JSON.stringify(before)!==JSON.stringify(await snapshotAllStores()))return false;
          await performReset({test:true});const reset=await snapshotAllStores();checkRunner(reset);
          return reset.runnerPlays.length===3&&reset.runnerPlays.every(p=>p.profile==='student');
        }"""))

    def test_all_unlocks_tie_order_and_gameover_never_unlock(self):
        self.assertTrue(self.page.evaluate("""()=>{
          const d=runnerFixture();d.runnerPlays=[];d.coinSpends=d.coinSpends.filter(s=>s.game==='crane');
          addRunner(d,'z','student','S01','goldfish',100,'finished','gameover');
          if(summarizeRunnerPlays(d.runnerPlays,'student').unlockedStageIds.length!==1)return false;
          for(const stage of RUNNER_STAGE_IDS)addRunner(d,stage,'student',stage,'shiba',0);
          addRunner(d,'a','student','S01','shiba',100);
          addRunner(d,'b','student','S01','shiba',100);
          checkRunner(d);
          const summary=summarizeRunnerPlays([...d.runnerPlays].reverse(),'student');
          return summary.unlockedStageIds.join()===RUNNER_STAGE_IDS.join()&&summary.bestByStage.S01.id==='a';
        }"""))
