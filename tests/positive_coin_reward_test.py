"""Issue #32: 正解時の最低報酬・原子的保存・v8互換を架空データで検証。

実行: PYTHONPATH=tests python -m unittest positive_coin_reward_test -v
Chromiumでの検証であり、Safari実機の複数タブ・タッチ操作は別途確認する。
"""
import json
from pathlib import Path
import unittest

import quiz_coin_display_test as coins


class PositiveCoinRewardTest(unittest.TestCase):
    # 既存のブラウザ準備・操作だけを共用し、無関係なテストは継承しない。
    setUpClass = classmethod(coins.QuizCoinDisplayTest.setUpClass.__func__)
    tearDownClass = classmethod(coins.QuizCoinDisplayTest.tearDownClass.__func__)
    setUp = coins.QuizCoinDisplayTest.setUp
    tearDown = coins.QuizCoinDisplayTest.tearDown
    ready = coins.QuizCoinDisplayTest.ready
    install = coins.QuizCoinDisplayTest.install
    snapshot = coins.QuizCoinDisplayTest.snapshot
    quiz = coins.QuizCoinDisplayTest.quiz
    screen = coins.QuizCoinDisplayTest.screen
    answer = coins.QuizCoinDisplayTest.answer
    second_tab = coins.QuizCoinDisplayTest.second_tab
    balance = coins.QuizCoinDisplayTest.balance
    next_question = coins.QuizCoinDisplayTest.next_question

    def fallback_question(self):
        self.quiz()
        self.answer()
        self.next_question()
        self.answer(correct=False)
        self.next_question()
        self.balance(2)

    def test_all_difficulties_keep_existing_rewards_and_fill_only_zero_correct(self):
        for difficulty, minimum, master in [('basic', 2, 3), ('standard', 4, 6),
                                             ('advanced', 6, 9), (None, 2, 3)]:
            with self.subTest(difficulty=difficulty):
                self.install()
                self.page.evaluate("""async difficulty=>{
                  const q={...QUESTIONS.find(q=>q.era==='E01')};
                  if(difficulty)q.difficulty=difficulty;else delete q.difficulty;
                  const tx=db.transaction('questions','readwrite');tx.objectStore('questions').put(q);
                  await new Promise(resolve=>tx.oncomplete=resolve);await loadImportedQuestions();
                }""", difficulty)
                self.quiz()
                # 初正解→誤答→正解→初習得→復習→誤答→正解→再習得→復習。
                steps = [(True, minimum, 'first', '初正解ボーナス'),
                         (False, 0, None, None),
                         (True, minimum, 'correct', '正解ボーナス'),
                         (True, master, 'master', '初習得ボーナス'),
                         (True, minimum, 'review', '復習ボーナス'),
                         (False, 0, None, None),
                         (True, minimum, 'correct', '正解ボーナス'),
                         (True, minimum, 'correct', '正解ボーナス'),
                         (True, minimum, 'review', '復習ボーナス')]
                total = 0
                for i, (correct, amount, stage, label) in enumerate(steps):
                    if i:
                        self.next_question()
                    self.answer(correct)
                    total += amount
                    self.balance(total)
                    saved = self.page.evaluate('({amount:currentSession.coinAward,stages:currentSession.coinStages})')
                    self.assertEqual(saved, {'amount': amount, 'stages': [stage] if stage else []})
                    result = self.page.locator('#result').inner_text()
                    if correct:
                        self.assertIn(f'+{amount} コイン獲得！', result)
                        self.assertTrue(self.page.locator('.coin-reward small').inner_text().endswith(label))
                        self.assertNotIn('0枚', result)
                        # 保存された金額・種類が再読み込み後にも変わらない。
                        before = self.snapshot()
                        self.page.reload()
                        self.ready()
                        self.balance(total)
                        self.assertEqual(self.page.locator('#result').inner_text(), result)
                        self.assertEqual(self.snapshot(), before)
                    else:
                        self.assertNotIn('コイン獲得', result)
                after = self.snapshot()
                self.assertEqual(len(after['answers']), 9)
                self.assertEqual(len(after['coinClaims']), 2)
                self.assertEqual(len(after['coinEvents']), 2)
                self.assertEqual(len(after['reviewEvents']), 5)
                self.assertEqual({r['difficulty'] for r in after['reviewEvents']}, {difficulty or 'basic'})
                # 全報酬が、変更していない既存v8検証条件を満たす。
                self.assertEqual(self.page.evaluate('data=>validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:8,data})', after), after)

    def test_simultaneous_first_and_master_rewards_keep_combined_display_without_top_up(self):
        self.quiz()
        self.answer()
        # 旧履歴などで進捗だけがあり、両段階の受取記録がない場合。
        self.page.evaluate("""async()=>{
          const tx=db.transaction(['coinClaims','coinEvents'],'readwrite');
          tx.objectStore('coinClaims').clear();tx.objectStore('coinEvents').clear();
          await new Promise(resolve=>tx.oncomplete=resolve);
        }""")
        self.next_question()
        self.answer()
        self.balance(5)
        self.assertEqual(self.page.evaluate('currentSession.coinStages'), ['first', 'master'])
        self.assertIn('初正解＆初習得ボーナス', self.page.locator('#result').inner_text())
        self.assertEqual(len(self.snapshot()['reviewEvents']), 0)
        before = self.snapshot()
        result = self.page.locator('#result').inner_text()
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.locator('#result').inner_text(), result)
        self.assertEqual(self.snapshot(), before)

    def test_double_submit_and_same_answer_token_cannot_duplicate_fallback(self):
        self.fallback_question()
        before = self.snapshot()
        self.page.evaluate("""async()=>{
          const original=saveAnswer;
          saveAnswer=(...args)=>{window.savedArgs=structuredClone(args);return original(...args);};
          selected=[...currentQuestion.answers];updateChoices();
          await Promise.all([grade(),grade(),grade()]);saveAnswer=original;
        }""")
        self.balance(4)
        after = self.snapshot()
        self.assertEqual(len(after['answers']), len(before['answers']) + 1)
        self.assertEqual(len(after['reviewEvents']), 1)
        # 同じトークンでの再送もセッション検査により拒否。
        rejected = self.page.evaluate('async()=>{try{await saveAnswer(...savedArgs);return false;}catch{return true;}}')
        self.assertTrue(rejected)
        self.assertEqual(self.snapshot(), after)

    def test_two_tabs_commit_only_one_fallback_without_web_locks(self):
        self.fallback_question()
        other = self.second_tab()
        self.quiz(page=other)
        before = self.snapshot()
        for page in [self.page, other]:
            page.evaluate("""()=>{
              Object.defineProperty(navigator,'locks',{configurable:true,value:undefined});
              const original=saveAnswer;
              saveAnswer=async(...args)=>{await new Promise(r=>window.releaseSave=r);return original(...args);};
              selected=[...currentQuestion.answers];window.answering=grade();
            }""")
            page.wait_for_function('typeof releaseSave==="function"')
        # 両タブの回答が同じ保存前状態を読んだ後、競合する保存を開始。
        for page in [self.page, other]:
            page.evaluate('()=>{releaseSave();}')
        for page in [self.page, other]:
            page.evaluate('async()=>{await answering;}')
            self.balance(4, page)
            self.assertIn('正解ボーナス', page.locator('#result').inner_text())
        after = self.snapshot()
        self.assertEqual(len(after['answers']), len(before['answers']) + 1)
        self.assertEqual(len(after['reviewEvents']), 1)
        self.assertEqual(after['coinClaims'], before['coinClaims'])
        self.assertEqual(after['coinEvents'], before['coinEvents'])

    def test_abort_after_reward_write_rolls_back_all_stores_and_retry_awards_once(self):
        self.fallback_question()
        before = self.snapshot()
        self.page.evaluate("""()=>{
          window.originalAdd=IDBObjectStore.prototype.add;window.rewardWritten=false;
          IDBObjectStore.prototype.add=function(...args){
            const req=originalAdd.apply(this,args);
            if(this.name==='reviewEvents')req.addEventListener('success',()=>window.rewardWritten=true);
            if(this.name==='answers')req.addEventListener('success',()=>this.transaction.abort());
            return req;
          };
        }""")
        self.answer()
        self.assertTrue(self.page.evaluate('rewardWritten'))
        self.balance(2)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.page.locator('#result').is_hidden())
        self.page.evaluate('()=>{IDBObjectStore.prototype.add=originalAdd;}')
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), before)
        self.answer()
        self.balance(4)
        self.assertEqual(len(self.snapshot()['reviewEvents']), 1)

    def test_profiles_have_independent_fallbacks_claims_and_balances(self):
        for who in ['student', 'test']:
            self.page.evaluate('who=>navigateHome(who)', who)
            self.fallback_question()
            self.answer()
            self.balance(4)
        saved = self.snapshot()
        for who in ['student', 'test']:
            self.assertEqual(self.page.evaluate('who=>getAvailableCoins(who)', who), 4)
            self.assertEqual(len([r for r in saved['reviewEvents'] if r['profile'] == who]), 1)
            self.assertEqual(len([r for r in saved['coinClaims'] if r['profile'] == who]), 1)
        self.assertEqual(len({r['key'] for r in saved['reviewEvents']}), 2)

    def test_v8_export_validate_preview_restore_preserves_fallback_and_existing_data(self):
        # 既存のカード・景品・消費・復習履歴を残した状態で新報酬を獲得。
        self.page.evaluate("""async()=>{
          const data=plushFixture(['shiba'],'student');
          data.sampleSettings=SAMPLE_QUESTIONS.map(q=>({id:q.id,hidden:true}));
          await plushInstall(data);await navigateHome('student');
        }""")
        self.quiz()
        self.answer(correct=False)
        self.next_question()
        self.answer()
        self.balance(707)
        before = self.snapshot()
        result = self.page.locator('#result').inner_text()
        self.page.locator('#open-admin').click()
        self.page.locator('#admin-backup-group > summary').click()
        self.page.locator('#toggle-backup').click()
        with self.page.expect_download() as event:
            self.page.locator('#backup-export').click()
        backup = json.loads(Path(event.value.path()).read_text())
        self.assertEqual(backup['backupVersion'], 8)
        self.assertEqual(backup['data'], before)
        # 補完報酬でも既存の検証（額・キー・重複・プロフィール）を緩めない。
        self.assertTrue(self.page.evaluate("""data=>[
          d=>d.reviewEvents[0].amount=0,
          d=>d.reviewEvents[0].amount=3,
          d=>d.reviewEvents[0].key='invalid',
          d=>d.reviewEvents.push({...d.reviewEvents[0]}),
          d=>d.reviewEvents[0].profile=d.reviewEvents[0].profile==='test'?'student':'test'
        ].every(mutate=>{
          const copy=structuredClone(data);mutate(copy);
          try{validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:8,data:copy});return false;}catch{return true;}
        })""", before))
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate("""async()=>{
          const data=await snapshotAllStores();
          const event=data.answers[data.answers.length-1];
          data.reviewEvents=data.reviewEvents.filter(r=>r.key!==`review:student:${event.token}`);
          data.sessions.find(s=>s.profile==='student').coinAward=0;
          data.sessions.find(s=>s.profile==='student').coinStages=[];
          await replaceAllStores(data);
        }""")
        changed = self.snapshot()
        self.assertNotEqual(changed, before)
        self.page.locator('#backup-file').set_input_files({
            'name': 'synthetic-issue32-v8.json', 'mimeType': 'application/json',
            'buffer': json.dumps(backup).encode()})
        self.page.wait_for_function('document.querySelector("#backup-preview").textContent.startsWith("検査OK")')
        self.assertEqual(self.snapshot(), changed, 'プレビューは読み取りだけ')
        self.page.locator('#backup-restore').click()
        self.page.wait_for_function('!backingUp&&pendingRestore===null')
        self.assertEqual(self.snapshot(), before)
        self.page.reload()
        self.ready()
        self.quiz()
        self.balance(707)
        self.assertEqual(self.page.locator('#result').inner_text(), result)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'), [8, 8, 15])

    def test_old_zero_result_is_read_without_retroactive_payment(self):
        self.fallback_question()
        self.answer()
        self.page.evaluate("""async()=>{
          const data=await snapshotAllStores();
          data.reviewEvents=[];
          data.sessions[0].coinAward=0;data.sessions[0].coinStages=[];
          // tokenのない旧回答履歴も読み込み可能。
          data.answers.forEach(ev=>delete ev.token);
          await replaceAllStores(validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:8,data}));
        }""")
        before = self.snapshot()
        self.page.reload()
        self.ready()
        self.balance(2)
        self.assertEqual(self.page.evaluate('phase'), 'result')
        self.assertNotIn('コイン獲得', self.page.locator('#result').inner_text())
        self.assertNotIn('0枚', self.page.locator('#result').inner_text())
        self.assertEqual(self.snapshot(), before)
        self.next_question()
        self.answer()
        self.balance(5)  # 次の初習得報酬だけを獲得。
