"""PR #35 + #36: 全モードの報酬とセット保存を架空データのみで検証。

弱点モードでは習得済みを出題しないため、習得後の復習・誤答は時代別から
行い、同じ問題が苦手へ戻ることと全モードの共通履歴を検証する。
"""
import json
from pathlib import Path
import unittest

import study_modes_test as study
from plush_test import FIXTURE_HELPERS


class StudyCoinIntegrationTest(unittest.TestCase):
    setUpClass = classmethod(study.StudyModesTest.setUpClass.__func__)
    tearDownClass = classmethod(study.StudyModesTest.tearDownClass.__func__)
    setUp = study.StudyModesTest.setUp
    tearDown = study.StudyModesTest.tearDown
    ready = study.StudyModesTest.ready
    screen = study.StudyModesTest.screen
    snapshot = study.StudyModesTest.snapshot
    install = study.StudyModesTest.install
    start = study.StudyModesTest.start
    answer = study.StudyModesTest.answer
    second_tab = study.StudyModesTest.second_tab
    return_event = study.StudyModesTest.return_event

    def seed(self, difficulty='basic', claimed=False, count=1):
        # サブケース間で保存失敗・遅延送信の注入を持ち越さない。
        self.page.reload();self.ready()
        self.page.evaluate(FIXTURE_HELPERS)
        self.install(count, count)
        self.page.evaluate("""async ({difficulty,claimed})=>{
          const data=await snapshotAllStores(),at='2020-01-01T00:00:00.000Z';
          data.questions=data.questions.map(q=>{
            const copy={...q,era:'E01',tag:'culture',answers:[0]};
            if(difficulty)copy.difficulty=difficulty;else delete copy.difficulty;return copy;
          });
          data.progress=data.questions.flatMap(q=>['student','test'].map(profile=>({
            key:`${profile}:${q.id}`,profile,questionId:q.id,revision:1,attempts:1,streak:0,
            mastered:false,everWrong:true,lastAnsweredAt:at})));
          if(claimed)for(const q of data.questions)for(const profile of ['student','test'])for(const stage of ['first','master']) {
            const key=coinClaimKey(profile,q.id,stage);
            data.coinClaims.push({key,profile,questionId:q.id,stage,source:'reward',claimedAt:at});
            data.coinEvents.push({key,profile,questionId:q.id,stage,difficulty:difficulty||'basic',amount:COIN_REWARDS[difficulty||'basic'][stage],at});
          }
          await plushInstall(data);await navigateHome('student');
        }""", {'difficulty':difficulty,'claimed':claimed})

    def begin(self, mode, page=None):
        page=page or self.page
        if mode=='era':
            page.evaluate("""async()=>{
              await startEra('E01');
              if(phase==='result')await advance('E01',currentQuestion.id);
            }""")
            page.wait_for_function('quizReady&&phase==="question"')
        else:
            self.start(mode, 'culture' if mode=='genre' else None, page)

    def result(self, page=None):
        page=page or self.page
        return page.locator('#study-last-result' if page.evaluate('phase==="complete"') else '#result')

    def test_rewards_all_modes_difficulties_relearning_and_reload(self):
        steps=[(True, 'first'),(False,None),(True,'correct'),(True,'master'),
               (True,'review'),(False,None),(True,'correct'),(True,'correct'),(True,'review')]
        labels={'first':'初正解ボーナス','master':'初習得ボーナス','correct':'正解ボーナス','review':'復習ボーナス'}
        for mode in ['era','weak','genre']:
            for difficulty,minimum,master in [('basic',2,3),('standard',4,6),('advanced',6,9),(None,2,3)]:
                with self.subTest(mode=mode,difficulty=difficulty):
                    self.seed(difficulty)
                    total=0
                    for i,(correct,stage) in enumerate(steps):
                        # 習得済みを弱点に混入させず、他モードで共有状態を変える。
                        actual='era' if mode=='weak' and i in [4,5,8] else mode
                        if mode=='weak' and i==4:
                            self.begin('weak')
                            self.assertEqual(self.page.evaluate('phase'), 'complete')
                            self.assertEqual(self.page.evaluate('currentSession.entries'), [])
                        self.begin(actual)
                        self.answer(correct)
                        amount=0 if not correct else master if stage=='master' else minimum
                        total+=amount
                        self.assertEqual(self.page.evaluate('({amount:currentSession.coinAward,stages:currentSession.coinStages})'),
                                         {'amount':amount,'stages':[stage] if stage else []})
                        self.assertEqual(self.page.evaluate('getAvailableCoins()'),total)
                        text=self.result().inner_text()
                        if correct:
                            self.assertIn(f'+{amount} コイン獲得！',text)
                            self.assertIn(labels[stage],self.result().locator('small').inner_text())
                        else:self.assertNotIn('コイン獲得',text)
                        if i in [2,3,7]:
                            before=self.snapshot()
                            self.page.reload();self.ready()
                            self.assertEqual(self.result().inner_text(),text)
                            self.assertEqual(self.snapshot(),before)
                            self.return_event()
                            self.assertEqual(self.snapshot(),before)
                    state=self.snapshot()
                    self.assertEqual(len(state['answers']),9)
                    self.assertEqual(len(state['coinClaims']),2)
                    self.assertEqual(len(state['coinEvents']),2)
                    self.assertEqual(len(state['reviewEvents']),5)
                    self.assertEqual([p for p in state['progress'] if p['profile']=='test'][0]['attempts'],1)

    def test_double_submit_and_uuid_replay_all_modes(self):
        for mode in ['era','weak','genre']:
            with self.subTest(mode=mode):
                self.seed(claimed=True)
                self.begin(mode)
                before=self.snapshot()
                self.page.evaluate("""async()=>{
                  const original=saveAnswer;
                  saveAnswer=(...args)=>{window.submittedArgs=structuredClone(args);return original(...args);};
                  selected=[...currentQuestion.answers];updateChoices();
                  try{await Promise.all([grade(),grade(),grade()]);}finally{saveAnswer=original;}
                }""")
                after=self.snapshot()
                self.assertEqual(len(after['answers']),len(before['answers'])+1)
                self.assertEqual(len(after['reviewEvents']),1)
                self.assertEqual(self.page.evaluate('getAvailableCoins()'),7)
                self.assertEqual(self.page.evaluate('currentSession.coinStages'),['correct'])
                rejected=self.page.evaluate('async()=>{try{await saveAnswer(...submittedArgs);return false;}catch{return true;}}')
                self.assertTrue(rejected)
                self.assertEqual(self.snapshot(),after)

    def test_two_tabs_without_locks_commit_one_final_reward_all_modes(self):
        for mode in ['era','weak','genre']:
            with self.subTest(mode=mode):
                self.seed(claimed=True)
                self.begin(mode)
                other=self.second_tab()
                self.begin(mode,other)
                before=self.snapshot()
                for page in [self.page,other]:
                    page.evaluate("""()=>{
                      Object.defineProperty(navigator,'locks',{configurable:true,value:undefined});
                      const original=saveAnswer;
                      saveAnswer=async(...args)=>{await new Promise(r=>window.releaseSave=r);return original(...args);};
                      selected=[...currentQuestion.answers];window.answering=grade();
                    }""")
                    page.wait_for_function('typeof releaseSave==="function"')
                for page in [self.page,other]:page.evaluate('()=>{releaseSave();}')
                for page in [self.page,other]:
                    page.evaluate('async()=>{await answering;}')
                    self.assertEqual(page.evaluate('getAvailableCoins()'),7)
                    self.assertIn('正解ボーナス',self.result(page).inner_text())
                after=self.snapshot()
                self.assertEqual(len(after['answers']),len(before['answers'])+1)
                self.assertEqual(len(after['reviewEvents']),1)
                if mode!='era':
                    s=next(s for s in after['studySets'] if s['mode']==mode)
                    self.assertEqual(s['phase'],'complete')
                    self.assertEqual(len(s['results']),1)
                other.close()

    def test_abort_after_bonus_rolls_back_progress_reward_and_final_set_all_modes(self):
        for mode in ['era','weak','genre']:
            with self.subTest(mode=mode):
                self.seed(claimed=True)
                self.begin(mode)
                before=self.snapshot()
                self.page.evaluate("""()=>{
                  window.originalAdd=IDBObjectStore.prototype.add;window.bonusWritten=false;
                  IDBObjectStore.prototype.add=function(...args){
                    const req=originalAdd.apply(this,args);
                    if(this.name==='reviewEvents')req.addEventListener('success',()=>window.bonusWritten=true);
                    if(this.name==='answers')req.addEventListener('success',()=>this.transaction.abort());
                    return req;
                  };
                }""")
                self.answer()
                self.assertTrue(self.page.evaluate('bonusWritten'))
                self.assertEqual(self.snapshot(),before)
                self.assertEqual(self.page.evaluate('phase'),'question')
                self.page.evaluate('()=>{IDBObjectStore.prototype.add=originalAdd;}')
                self.page.reload();self.ready()
                self.assertEqual(self.snapshot(),before)
                self.answer()
                self.assertEqual(self.page.evaluate('getAvailableCoins()'),7)
                self.assertEqual(len(self.snapshot()['reviewEvents']),1)
                self.assertEqual(self.page.evaluate('phase'),'result' if mode=='era' else 'complete')

    def test_tenth_answer_bonus_completion_and_v9_export_restore(self):
        for mode in ['weak','genre']:
            with self.subTest(mode=mode):
                self.seed('advanced',claimed=True,count=10)
                self.begin(mode)
                initial=self.page.evaluate('currentSession.entries')
                for i in range(10):
                    self.answer()
                    self.assertEqual(self.page.evaluate('currentSession.entries'),initial)
                    self.assertEqual(self.page.evaluate('currentSession.coinAward'),6)
                    self.assertEqual(self.page.evaluate('currentSession.coinStages'),['correct'])
                    if i<9:self.page.evaluate('nextStudy()')
                self.screen('study-finished')
                self.assertIn('正解ボーナス',self.result().inner_text())
                self.assertIn('+6 コイン獲得',self.result().inner_text())
                self.assertIn('回答数 10問 ｜ 正解数 10問',self.page.locator('#study-result-summary').inner_text())
                before=self.snapshot()
                self.assertEqual(len(before['answers']),10)
                self.assertEqual(len(before['reviewEvents']),10)
                self.assertEqual(self.page.evaluate('getAvailableCoins()'),210)
                self.page.reload();self.ready()
                self.assertEqual(self.snapshot(),before)
                self.page.evaluate('navigate("admin")')
                self.page.locator('#admin-backup-group > summary').click()
                self.page.locator('#toggle-backup').click()
                with self.page.expect_download() as event:self.page.locator('#backup-export').click()
                backup=json.loads(Path(event.value.path()).read_text())
                self.assertEqual(backup['backupVersion'],9)
                self.assertEqual(backup['data'],before)
                self.page.evaluate("""async()=>{
                  const data=await snapshotAllStores();
                  data.studySets=[];data.reviewEvents=[];await replaceAllStores(data);
                }""")
                self.page.locator('#backup-file').set_input_files({'name':'synthetic-study-v9.json','mimeType':'application/json','buffer':json.dumps(backup).encode()})
                self.page.wait_for_function('pendingRestore!==null')
                self.page.locator('#backup-restore').click()
                self.page.wait_for_function('!backingUp&&pendingRestore===null')
                self.assertEqual(self.snapshot(),before)
                self.page.reload();self.ready()
                # 復元は管理画面へ戻るので、保存済みルートを明示的に復帰する。
                self.page.evaluate('mode=>restoreRoute({screen:"study",profile:"student",mode,genre:mode==="genre"?"culture":null})',mode)
                self.screen('study-finished')
                self.assertIn('正解ボーナス',self.result().inner_text())
                self.assertEqual(self.page.evaluate('currentSession.coinAward'),6)
                self.assertEqual(self.snapshot(),before)

    def test_midset_bonus_selection_and_profile_resume_are_independent(self):
        self.seed('standard',claimed=True,count=3)
        self.begin('weak')
        self.answer()
        weak=self.page.evaluate('currentSession')
        self.page.evaluate('navigateHome()')
        self.begin('genre')
        self.answer()
        genre=self.page.evaluate('currentSession')
        student=self.snapshot()
        self.page.evaluate('navigateHome("test")')
        for mode in ['era','weak','genre']:
            self.begin(mode)
            self.answer()
        after=self.snapshot()
        for name in ['progress','answers','coinClaims','coinEvents','reviewEvents','studySets']:
            self.assertEqual([r for r in after[name] if r['profile']=='student'],[r for r in student[name] if r['profile']=='student'])
        self.assertEqual(self.page.evaluate('getAvailableCoins("student")'),38)  # 初回分3×(4+6)と、今回の補完2×4。
        self.page.evaluate('navigateHome("student")')
        self.begin('weak')
        self.assertEqual(self.page.evaluate('currentSession'),weak)
        self.assertIn('正解ボーナス',self.result().inner_text())
        self.page.reload();self.ready()
        self.assertEqual(self.page.evaluate('currentSession'),weak)
        self.page.evaluate('navigateHome()')
        self.begin('genre')
        self.assertEqual(self.page.evaluate('currentSession'),genre)
        self.assertIn('正解ボーナス',self.result().inner_text())

    def test_common_era_weak_genre_answers_use_single_history_and_claims(self):
        self.seed()
        for mode in ['era','weak','genre']:
            self.begin(mode)
            self.answer()
        state=self.snapshot()
        self.assertEqual(len(state['answers']),3)
        self.assertEqual(len(state['coinClaims']),2)
        self.assertEqual(len(state['coinEvents']),2)
        self.assertEqual(len(state['reviewEvents']),1)
        self.assertEqual(self.page.evaluate('getAvailableCoins()'),7)
        self.assertTrue(next(p for p in state['progress'] if p['profile']=='student')['mastered'])

    def test_pr36_v8_bonus_migrates_and_legacy_restore_keeps_reward(self):
        import subprocess
        source=subprocess.check_output(['git','show','439f7b887719d2ff1a2ecfd595c0d3299a1e048d:index.html'],text=True)
        context=self.browser.new_context()
        page=context.new_page()
        page.on('dialog',lambda dialog:dialog.accept())
        page.route(self.url,lambda route:route.fulfill(body=source,content_type='text/html'))
        try:
            page.goto(self.url);self.ready(page)
            page.evaluate(FIXTURE_HELPERS)
            page.evaluate("""async()=>{
              const data=plushFixture();
              data.sampleSettings=SAMPLE_QUESTIONS.map(q=>({id:q.id,hidden:true}));
              data.reviewEvents=[];data.awards=[];data.sessions=[];
              const p=data.progress.find(p=>p.profile==='student');
              p.streak=0;p.mastered=false;p.everWrong=true;p.attempts=3;
              await plushInstall(data);await ensureArcadeBoards();await navigateHome('student');
              await startEra('E01');selected=[...currentQuestion.answers];updateChoices();await grade();
            }""")
            self.assertEqual(page.evaluate('[DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'),[8,8,15])
            self.assertEqual(page.evaluate('currentSession.coinStages'),['correct'])
            self.assertEqual(page.evaluate('currentSession.coinAward'),2)
            before=self.snapshot(page)
            legacy={'backupFormat':'history-master-backup','backupVersion':8,'data':before}
            page.unroute(self.url)
            page.reload();self.ready(page)
            self.assertEqual(page.evaluate('[APP_VERSION,DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'),['v1.7.1',9,9,16])
            after=self.snapshot(page)
            for name in before:self.assertEqual(after[name],before[name],name)
            self.assertEqual(after['studySets'],[])
            self.assertIn('正解ボーナス',page.locator('#result').inner_text())
            self.start('genre','culture',page)
            self.assertEqual(len(self.snapshot(page)['studySets']),1)
            page.evaluate('navigate("admin")')
            page.locator('#admin-backup-group > summary').click()
            page.locator('#toggle-backup').click()
            page.locator('#backup-file').set_input_files({'name':'synthetic-pr36-v8.json','mimeType':'application/json','buffer':json.dumps(legacy).encode()})
            page.wait_for_function('pendingRestore!==null')
            self.assertIn('途中セットを破棄',page.locator('#backup-preview').inner_text())
            page.locator('#backup-restore').click()
            page.wait_for_function('!backingUp&&pendingRestore===null')
            self.assertEqual(self.snapshot(page),after)
            page.reload();self.ready(page)
            page.evaluate('startEra("E01")')
            self.assertIn('正解ボーナス',page.locator('#result').inner_text())
            self.assertEqual(page.evaluate('currentSession.coinAward'),2)
            self.assertEqual(self.snapshot(page),after)
        finally:context.close()
