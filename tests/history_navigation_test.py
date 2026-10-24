"""Issue #13: Chromiumで履歴・保存・ページ復帰を検証。すべて架空データ。

PageTransitionEventの注入は復帰ハンドラの検証であり、Safari実機のbfcache保証ではない。
"""
import functools
import http.server
import os
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright
from plush_test import FIXTURE_HELPERS, ROOT, QuietHandler


class HistoryNavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get('HISTORY_MASTER_BROWSER') or shutil.which('chromium'))
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/index.html'

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('dialog', lambda dialog: dialog.accept('初期化') if dialog.type=='prompt' else dialog.accept())
        self.page.goto(self.url)
        self.ready()
        self.install()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def ready(self, page=None):
        (page or self.page).wait_for_function('appReady')

    def install(self, mastered=False):
        self.page.evaluate(FIXTURE_HELPERS)
        self.page.evaluate("""async mastered=>{
          const data=plushFixture();
          data.sampleSettings=SAMPLE_QUESTIONS.map(q=>({id:q.id,hidden:true}));
          data.questions[0].options=['架空の甲','架空の乙','架空の丙'];
          data.questions[0].shuffleOptions=true;
          data.questions.push({...data.questions[0],id:'TEST-NAV-004',era:'E04',q:'別時代の架空問題です。'});
          if(!mastered)for(const name of ['progress','sessions','answers','awards','coinClaims','coinEvents','reviewEvents'])data[name]=[];
          else for(const sess of data.sessions)sess.optionOrder=[2,0,1];
          await plushInstall(data);await navigateHome('student');
        }""", mastered)

    def snapshot(self, page=None):
        return (page or self.page).evaluate('snapshotAllStores()')

    def quiz(self, era='E01', page=None):
        page = page or self.page
        page.evaluate('era=>startEra(era)', era)
        self.screen('quiz', page)
        page.wait_for_function('quizReady')

    def screen(self, screen, page=None):
        (page or self.page).wait_for_function(
            'id=>!document.getElementById(id).classList.contains("hidden")', arg=screen)

    def back(self, screen, page=None):
        page = page or self.page
        page.go_back()
        self.screen(screen, page)
        if screen == 'quiz':
            page.wait_for_function('quizReady')

    def forward(self, screen, page=None):
        page = page or self.page
        page.go_forward()
        self.screen(screen, page)
        if screen == 'quiz':
            page.wait_for_function('quizReady')

    def answer(self, correct=True, page=None):
        page = page or self.page
        page.evaluate('correct=>{selected=correct?[...currentQuestion.answers]:[1];updateChoices();}', correct)
        page.evaluate('grade()')
        page.wait_for_function('!saving&&quizReady')

    def return_event(self, page=None):
        (page or self.page).evaluate("""async()=>{
          const original=reconcilePage;
          try {
            reconcilePage=(...args)=>window.eventRestoration=original(...args);
            dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
            await window.eventRestoration;
          } finally {reconcilePage=original;}
        }""")

    def second_tab(self):
        page = self.context.new_page()
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        page.goto(self.url)
        self.ready(page)
        return page

    def test_back_forward_repeatedly_keeps_history_and_all_stores(self):
        initial_length = self.page.evaluate('history.length')
        self.quiz()
        before = self.snapshot()
        self.assertEqual(self.page.evaluate('history.length'), initial_length + 1)
        for _ in range(5):
            self.back('home')
            self.forward('quiz')
        self.assertEqual(self.page.evaluate('history.length'), initial_length + 1)
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('async()=>{await renderHome();show("admin");show("quiz");}')
        self.assertEqual(self.page.evaluate('history.length'), initial_length + 1)

    def test_unanswered_question_order_and_tab_draft_survive_restore(self):
        self.quiz()
        self.page.locator('#choices button').nth(1).click()
        before = self.page.evaluate('({id:currentQuestion.id,order:optionOrder,selected})')
        stores = self.snapshot()
        self.back('home')
        self.forward('quiz')
        self.return_event()
        self.assertEqual(self.page.evaluate('({id:currentQuestion.id,order:optionOrder,selected})'), before)
        self.assertEqual(self.snapshot(), stores)
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.evaluate('currentQuestion.id'), before['id'])
        self.assertEqual(self.page.evaluate('optionOrder'), before['order'])
        self.assertEqual(self.page.evaluate('phase'), 'question')
        self.assertEqual(self.snapshot(), stores)

    def test_answered_restore_never_grades_or_changes_rewards(self):
        self.quiz()
        self.answer()
        before = self.snapshot()
        result = self.page.locator('#result').inner_text()
        self.page.evaluate('()=>{grade=saveAnswer=()=>{throw new Error("復帰時の再採点");};}')
        for _ in range(3):
            self.back('home')
            self.forward('quiz')
            self.return_event()
        self.assertEqual(self.page.locator('#result').inner_text(), result)
        self.assertIn('+2 コイン獲得', result)
        self.assertEqual(self.snapshot(), before)
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.locator('#result').inner_text(), result)
        self.assertEqual(self.snapshot(), before)

    def test_next_and_different_era_restore_current_session_not_past_questions(self):
        # 複数問題からの抽選でも、履歴は問題単位では増やさない。
        self.page.evaluate("""async()=>{
          const q={...QUESTIONS.find(q=>q.era==='E01'),id:'TEST-NAV-002',q:'二つ目の架空問題です。'};
          const tx=db.transaction('questions','readwrite');tx.objectStore('questions').put(q);
          await new Promise(r=>tx.oncomplete=r);await loadImportedQuestions();
        }""")
        self.quiz()
        self.answer()
        length = self.page.evaluate('history.length')
        previous = self.page.evaluate('currentQuestion.id')
        self.page.locator('#next').click()
        self.page.wait_for_function('id=>quizReady&&currentQuestion.id!==id', arg=previous)
        current = self.page.evaluate('currentQuestion.id')
        self.assertEqual(self.page.evaluate('history.length'), length)
        self.back('home')
        self.forward('quiz')
        self.assertEqual(self.page.evaluate('currentQuestion.id'), current)
        self.back('home')
        self.quiz('E04')
        self.assertEqual(self.page.evaluate('currentEra'), 'E04')
        self.back('home')
        self.forward('quiz')
        self.assertEqual(self.page.evaluate('currentQuestion.id'), 'TEST-NAV-004')

    def hold_grade(self):
        self.page.evaluate("""()=>{
          window.savedReadOne=readOne;
          readOne=async(store,key)=>{
            if(store==='progress'&&!window.releaseGrade)await new Promise(r=>window.releaseGrade=r);
            return savedReadOne(store,key);
          };
          selected=[...currentQuestion.answers];updateChoices();window.submitting=grade();
        }""")
        self.page.wait_for_function('typeof releaseGrade==="function"')

    def release_grade(self):
        self.page.evaluate('async()=>{readOne=savedReadOne;releaseGrade();await submitting;}')

    def test_navigation_during_save_captures_answer_order_and_restores_committed_result(self):
        self.quiz()
        order = self.page.evaluate('[...optionOrder]')
        self.hold_grade()
        self.back('home')
        # 保存中の復帰は同じ処理の確定を待つ。
        self.page.go_forward()
        self.page.evaluate('optionOrder=[1,2,0];')
        self.release_grade()
        self.page.wait_for_function('quizReady&&phase==="result"')
        session = self.page.evaluate("readOne('sessions','student:E01')")
        self.assertEqual(session['optionOrder'], order)
        self.assertEqual(session['selected'], [0])
        after = self.snapshot()
        self.assertEqual(len(after['answers']), 1)
        self.assertEqual(sum(e['amount'] for e in after['coinEvents']), 2)
        self.assertEqual(self.page.locator('#choices button').evaluate_all(
            'bs=>bs.map(b=>+b.dataset.originalIndex)'), order)

    def test_game_home_during_save_is_safe_and_old_result_cannot_overwrite_home(self):
        self.quiz()
        self.hold_grade()
        self.page.locator('#back-home').click()
        self.screen('home')
        self.release_grade()
        self.page.evaluate('reconcilePage()')
        self.screen('home')
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '2')
        self.assertEqual(len(self.snapshot()['answers']), 1)
        self.back('quiz')
        self.assertEqual(self.page.evaluate('phase'), 'result')

    def test_profile_change_during_save_never_writes_test_data(self):
        self.page.evaluate("async()=>{await navigateHome('test');await navigateHome('student');}")
        self.quiz()
        self.hold_grade()
        self.page.go_back()
        self.page.go_back()
        self.page.wait_for_function("profile==='test'")
        self.release_grade()
        self.page.evaluate('reconcilePage()')
        self.assertEqual(self.page.evaluate('profile'), 'test')
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '0')
        after = self.snapshot()
        for name in ['answers', 'progress', 'sessions', 'coinEvents', 'reviewEvents']:
            self.assertTrue(all(r['profile'] == 'student' for r in after[name]), name)
        self.assertEqual(len(after['answers']), 1)

    def test_committed_save_then_immediate_document_reload_reads_saved_result(self):
        self.quiz()
        self.page.evaluate("""()=>{
          const original=saveAnswer;
          saveAnswer=async(...args)=>{const result=await original(...args);
            window.committed=true;await new Promise(()=>{});return result;};
          selected=[0];window.submitting=grade();
        }""")
        self.page.wait_for_function('window.committed')
        saved = self.snapshot()
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.evaluate('phase'), 'result')
        self.assertIn('+2 コイン獲得', self.page.locator('#result').inner_text())
        self.assertEqual(self.snapshot(), saved)

    def test_save_rejection_and_transaction_abort_keep_all_stores_unchanged(self):
        self.install(mastered=True)
        self.quiz()
        before = self.snapshot()
        # 復習報酬を書いた後、answersの成功イベント内で実トランザクションを中断。
        self.page.evaluate("""()=>{
          window.originalAdd=IDBObjectStore.prototype.add;
          IDBObjectStore.prototype.add=function(value,...args){
            const req=originalAdd.call(this,value,...args);
            if(this.name==='answers')req.addEventListener('success',()=>this.transaction.abort());
            return req;
          };
        }""")
        self.answer()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('phase'), 'question')
        self.assertTrue(self.page.locator('#result').is_hidden())
        self.page.evaluate('()=>{IDBObjectStore.prototype.add=originalAdd;}')
        self.return_event()
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('()=>{window.originalSave=saveAnswer;saveAnswer=async()=>{throw new Error("架空の保存失敗");};}')
        self.answer()
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('()=>{saveAnswer=originalSave;}')
        self.answer()
        self.assertEqual(len(self.snapshot()['answers']), len(before['answers']) + 1)
        self.assertEqual(self.page.evaluate("getAvailableCoins('student')"), 807)

    def test_second_tab_spend_updates_pageshow_reload_and_single_transaction_balance(self):
        self.install(mastered=True)
        other = self.second_tab()
        before = self.snapshot()
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '805')
        other.evaluate("purchaseCranePlay(newArcadePlay('student'))")
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '805')
        self.return_event()
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '705')
        after = self.snapshot()
        for name in ['coinEvents', 'reviewEvents', 'answers', 'progress']:
            self.assertEqual(after[name], before[name], name)
        self.assertEqual(len(after['coinSpends']), len(before['coinSpends']) + 1)
        transactions = self.page.evaluate("""async()=>{
          const original=db.transaction.bind(db),seen=[];
          db.transaction=(names,mode)=>{seen.push({names,mode});return original(names,mode);};
          try{return {balance:await getAvailableCoins('student'),seen};}finally{db.transaction=original;}
        }""")
        self.assertEqual(transactions, {'balance': 705, 'seen': [
            {'names': ['coinEvents', 'reviewEvents', 'coinSpends'], 'mode': 'readonly'}]})
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '705')
        self.assertEqual(self.snapshot(), after)

    def test_balance_read_failure_marks_value_unknown_and_recovers(self):
        self.install(mastered=True)
        self.page.evaluate("""()=>{
          window.originalBalance=getAvailableCoins;
          getAvailableCoins=async()=>{throw new Error('架空の読込エラー');};
        }""")
        self.page.evaluate('reconcilePage()')
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '確認できません')
        self.page.evaluate('()=>{getAvailableCoins=originalBalance;}')
        self.return_event()
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '805')

    def test_student_test_admin_quiz_arcade_history_is_separated(self):
        self.install(mastered=True)
        self.quiz()
        self.answer()
        student = self.snapshot()
        self.page.locator('#open-admin').click()
        self.screen('admin')
        self.page.locator('#admin-start-test').click()
        self.screen('home')
        self.page.wait_for_function("profile==='test'&&document.querySelector('#home-coin-amount').textContent==='9'")
        self.quiz()
        self.answer()
        self.page.locator('#back-home').click()
        self.screen('home')
        self.page.evaluate('openArcade()')
        self.assertEqual(self.page.locator('#arcade-balance').inner_text(), '∞（無料）')
        self.back('home')
        self.back('quiz')
        self.assertEqual(self.page.evaluate('[profile,phase]'), ['test', 'result'])
        for store, rows in student.items():
            self.assertEqual([r for r in self.snapshot()[store] if r.get('profile') == 'student'],
                             [r for r in rows if r.get('profile') == 'student'], store)

    def test_arcade_aiming_back_forward_page_return_requires_manual_resume(self):
        self.install(mastered=True)
        self.page.evaluate('openArcade()')
        self.page.evaluate('startCrane()')
        self.page.wait_for_function('arcadeSweepFrame!==null')
        before = self.snapshot()
        play_id = self.page.evaluate('arcadePlay.id')
        self.back('home')
        self.forward('arcade')
        # restoreRouteは画面表示後に保存プレイを非同期で取得する。
        self.page.wait_for_function("""arcadeResumeRequired&&arcadeSweepFrame===null&&
          document.querySelector('#crane-start').textContent.includes('追加料金なし')""")
        self.assertIn('追加料金なし', self.page.locator('#crane-start').inner_text())
        self.assertTrue(self.page.locator('#crane-start').is_visible())
        self.assertFalse(self.page.locator('#crane-start').is_disabled())
        self.page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
        self.return_event()
        self.assertIsNone(self.page.evaluate('arcadeSweepFrame'))
        self.assertEqual(self.page.evaluate('arcadePlay.id'), play_id)
        self.page.evaluate('startCrane()')
        self.page.wait_for_function('arcadeSweepFrame!==null')
        after = self.snapshot()
        for store in ['coinSpends', 'coinEvents', 'reviewEvents', 'arcadePrizes']:
            self.assertEqual(after[store], before[store], store)
        self.assertEqual(len(after['arcadePlays']), 1)

    def test_arcade_animation_interruption_leaves_committed_outcome_for_manual_resume(self):
        self.install(mastered=True)
        self.page.evaluate('openArcade()')
        self.page.evaluate('startCrane()')
        self.page.evaluate("""()=>{
          stopCraneSweep();arcadePlay.armX=NEW_PRIZE_POSITIONS[0];
          window.savedRandom=Math.random;Math.random=()=>0;
          window.catching=catchCrane();
        }""")
        self.page.wait_for_function("arcadePlay.status==='resolving'")
        self.back('home')
        self.page.evaluate('async()=>{await catching;Math.random=savedRandom;}')
        stores = self.snapshot()
        self.assertEqual(stores['arcadePlays'][0]['status'], 'resolving')
        self.assertEqual(stores['arcadePrizes'], [])
        self.forward('arcade')
        self.page.wait_for_function('!arcadeBusy&&arcadeResumeRequired')
        self.assertEqual(self.snapshot(), stores)
        self.page.evaluate('()=>{animateCraneOutcome=async()=>{};}')
        self.page.evaluate('startCrane()')
        finished = self.snapshot()
        self.assertEqual(len(finished['coinSpends']), 1)
        self.assertEqual(len(finished['arcadePrizes']), 1)
        self.page.evaluate('id=>finishCranePlay(id)', finished['arcadePlays'][0]['id'])
        self.return_event()
        self.assertEqual(self.snapshot(), finished)

    def test_delayed_home_and_quiz_renders_cannot_replace_admin_or_arcade(self):
        self.page.evaluate("""()=>{
          window.savedAll=readAll;
          readAll=async name=>{if(name==='progress')await new Promise(r=>window.releaseHome=r);return savedAll(name);};
          window.oldHome=renderHome();
        }""")
        self.page.wait_for_function('typeof window.releaseHome==="function"')
        self.page.locator('#open-admin').click()
        self.screen('admin')
        self.page.evaluate('async()=>{readAll=savedAll;releaseHome();await oldHome;}')
        self.screen('admin')
        self.page.evaluate("""()=>{
          window.savedQuizState=readQuizState;
          readQuizState=async(...args)=>{await new Promise(r=>window.releaseQuiz=r);return savedQuizState(...args);};
          window.oldQuiz=startEra('E01');
        }""")
        self.page.wait_for_function('typeof window.releaseQuiz==="function"')
        self.page.evaluate('openArcade()')
        self.page.evaluate('async()=>{readQuizState=savedQuizState;releaseQuiz();await oldQuiz;}')
        self.screen('arcade')
        self.assertIsNone(self.page.evaluate('currentQuestion'))

    def test_delayed_coin_and_arcade_reads_cannot_overwrite_new_profile(self):
        self.install(mastered=True)
        self.page.evaluate("""()=>{
          window.savedBalance=getAvailableCoins;
          getAvailableCoins=async who=>{const balance=await savedBalance(who);
            if(!window.releaseBalance)await new Promise(r=>window.releaseBalance=r);return balance;};
          window.oldCoins=refreshCoinDisplay();
        }""")
        self.page.wait_for_function('typeof window.releaseBalance==="function"')
        self.page.evaluate("async()=>{getAvailableCoins=savedBalance;await navigateHome('test');releaseBalance();await oldCoins;}")
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '9')
        self.page.evaluate("""()=>{
          window.savedLatest=latestArcadePlay;
          latestArcadePlay=async who=>{if(who==='test')await new Promise(r=>window.releaseArcade=r);return savedLatest(who);};
          window.oldArcade=openArcade();
        }""")
        self.page.wait_for_function('typeof window.releaseArcade==="function"')
        self.page.evaluate("async()=>{latestArcadePlay=savedLatest;await navigateHome('student');releaseArcade();await oldArcade;}")
        self.screen('home')
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '805')

    def test_external_entry_browser_back_and_in_game_home_fallback(self):
        external = self.url.replace('127.0.0.1', 'localhost').replace('index.html', 'README.md')
        self.page.goto(external)
        self.page.goto(self.url)
        self.ready()
        self.page.go_back()
        self.assertEqual(self.page.url, external)
        self.page.go_forward()
        self.ready()
        # 外部直後のエントリを問題画面としてリロードしても、ホーム操作は外へ戻さない。
        self.page.evaluate("advance('E01',null)")
        self.page.evaluate("history.replaceState({app:'history-master',version:1,screen:'quiz',profile:'student',era:'E01'},'')")
        self.page.reload()
        self.ready()
        self.page.locator('#back-home').click()
        self.screen('home')
        self.assertEqual(self.page.url, self.url)
        self.back('quiz')
        self.page.go_back()
        self.assertEqual(self.page.url, external)

    def test_direct_open_and_unknown_history_reload_have_safe_home_fallback(self):
        self.quiz()
        saved = self.snapshot()
        self.page.evaluate("history.replaceState({app:'unrelated'},'')")
        self.page.reload()
        self.ready()
        self.screen('home')
        self.assertEqual(self.page.evaluate('profile'), 'student')
        self.assertEqual(self.snapshot(), saved)
        self.quiz()
        self.assertEqual(self.snapshot(), saved)

    def test_reward_rules_and_v7_result_backup_roundtrip_preserve_fourteen_stores(self):
        self.quiz()
        expected = [2, 5, 7, 7, 7, 7, 9]
        for i, balance in enumerate(expected):
            if i:
                self.page.locator('#next').click()
                self.page.wait_for_function('quizReady&&phase==="question"')
            self.answer(correct=i != 3)
            self.assertEqual(self.page.evaluate('getAvailableCoins()'), balance)
        before = self.snapshot()
        self.assertEqual(len(before['answers']), 7)
        self.assertEqual(len(before['coinClaims']), 2)
        self.assertEqual(len(before['coinEvents']), 2)
        self.assertEqual(len(before['reviewEvents']), 2)
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'), [8, 8, 15])
        self.page.evaluate("""async data=>{
          const checked=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:7,data});
          await replaceAllStores(checked);
        }""", before)
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('phase'), 'result')

    def test_two_tabs_submitting_same_session_commit_only_once(self):
        self.quiz()
        other = self.second_tab()
        self.quiz(page=other)
        for page in [self.page, other]:
            page.evaluate("""()=>{
              window.savedSave=saveAnswer;
              saveAnswer=async(...args)=>{await new Promise(r=>window.releaseSave=r);return savedSave(...args);};
              selected=[0];window.answering=grade();
            }""")
            page.wait_for_function('typeof window.releaseSave==="function"')
        self.page.evaluate('async()=>{releaseSave();await answering;}')
        other.evaluate('async()=>{releaseSave();await answering;}')
        after = self.snapshot()
        self.assertEqual(len(after['answers']), 1)
        self.assertEqual(len(after['coinEvents']), 1)
        self.assertEqual(self.page.evaluate('getAvailableCoins()'), 2)
        self.assertEqual(other.evaluate('phase'), 'result')
        self.assertEqual(other.locator('#result').inner_text(), self.page.locator('#result').inner_text())

    def test_saved_reply_cannot_paint_result_over_other_tab_next_question(self):
        self.quiz()
        self.page.evaluate("""()=>{
          const original=saveAnswer;
          saveAnswer=async(...args)=>{const saved=await original(...args);
            window.committed=true;await new Promise(r=>window.releaseReply=r);return saved;};
          selected=[0];window.submitting=grade();
        }""")
        self.page.wait_for_function('window.committed===true')
        other=self.second_tab()
        self.quiz(page=other)
        other.locator('#next').click()
        other.wait_for_function('quizReady&&phase==="question"')
        before=self.snapshot()
        self.page.evaluate('async()=>{releaseReply();await submitting;}')
        self.assertEqual(self.page.evaluate('phase'),'question')
        self.assertTrue(self.page.locator('#result').is_hidden())
        self.assertEqual(self.snapshot(),before)


    def test_missing_session_history_falls_back_without_drawing_new_question(self):
        self.quiz()
        self.page.evaluate("""async()=>{
          const tx=db.transaction('sessions','readwrite');tx.objectStore('sessions').clear();
          await new Promise(r=>tx.oncomplete=r);
        }""")
        before=self.snapshot()
        length=self.page.evaluate('history.length')
        self.return_event()
        self.screen('home')
        self.assertEqual(self.page.evaluate('history.state.screen'),'home')
        self.assertEqual(self.page.evaluate('history.length'),length)
        self.assertEqual(self.snapshot(),before)

    def test_stale_same_question_after_other_tab_progress_is_rejected(self):
        self.quiz()
        other=self.second_tab()
        self.quiz(page=other)
        self.answer(page=other)
        other.locator('#next').click()
        other.wait_for_function('quizReady&&phase==="question"')
        # 1問しかない時代ではセッションの既存フィールドが再び同一になりうる。
        before=self.snapshot()
        self.answer()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.page.evaluate('phase'),'question')
        self.assertEqual(len(before['answers']),1)

    def test_initial_pageshow_does_not_redraw_and_visibility_return_reconciles(self):
        self.install(mastered=True)
        self.page.evaluate("""()=>{
          window.originalAdvance=advance;window.draws=0;
          advance=(...args)=>{draws++;return originalAdvance(...args);};
          dispatchEvent(new PageTransitionEvent('pageshow',{persisted:false}));
        }""")
        self.assertEqual(self.page.evaluate('draws'),0)
        self.quiz()
        before=self.snapshot()
        self.page.evaluate("""async()=>{
          Object.defineProperty(document,'hidden',{configurable:true,value:true});
          document.dispatchEvent(new Event('visibilitychange'));
          const original=reconcilePage;
          try {
            reconcilePage=(...args)=>window.visibleRestoration=original(...args);
            Object.defineProperty(document,'hidden',{configurable:true,value:false});
            document.dispatchEvent(new Event('visibilitychange'));
            await visibleRestoration;
          }finally{reconcilePage=original;delete document.hidden;}
        }""")
        self.assertEqual(self.page.evaluate('draws'),0)
        self.assertEqual(self.snapshot(),before)


    def test_two_tabs_first_draw_uses_compare_before_write_even_without_session(self):
        other=self.second_tab()
        for page in [self.page,other]:
            page.evaluate("""()=>{
              const original=writeSession;
              writeSession=async(...args)=>{await new Promise(r=>window.releaseDraw=r);return original(...args);};
              window.starting=startEra('E01').catch(()=>{});
            }""")
            page.wait_for_function('typeof window.releaseDraw==="function"')
        self.page.evaluate('async()=>{releaseDraw();await starting;}')
        first=self.snapshot()
        other.evaluate('async()=>{releaseDraw();await starting;}')
        self.assertEqual(self.snapshot(),first)
        self.assertEqual(other.evaluate('currentQuestion.id'),self.page.evaluate('currentQuestion.id'))
        self.assertEqual(other.evaluate('optionOrder'),self.page.evaluate('optionOrder'))

    def enter_test_admin(self):
        self.page.locator('#open-admin').click()
        self.page.locator('#admin-start-test').click()
        self.page.wait_for_function("profile==='test'&&history.state.screen==='home'")
        self.page.locator('#open-admin').click()
        self.screen('admin')
        self.assertEqual(self.page.evaluate('[profile,history.state.profile]'), ['test','test'])

    def assert_changed_profile_history(self):
        self.screen('admin')
        self.assertEqual(self.page.evaluate('[profile,history.state.profile,history.state.screen]'),
                         ['student','student','admin'])
        length=self.page.evaluate('history.length')
        self.return_event()
        self.assertEqual(self.page.evaluate('[profile,history.state.profile]'), ['student','student'])
        self.page.reload()
        self.ready()
        self.screen('admin')
        self.assertEqual(self.page.evaluate('[profile,history.state.profile]'), ['student','student'])
        self.back('home')
        self.page.wait_for_function("profile==='test'&&history.state.profile==='test'")
        self.forward('admin')
        self.page.wait_for_function("profile==='student'&&history.state.profile==='student'")
        self.assertEqual(self.page.evaluate('history.length'),length)
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'), [8,8,15])

    def test_test_admin_selected_reset_replaces_current_history_profile(self):
        self.install(mastered=True)
        before=self.snapshot()
        self.enter_test_admin()
        length=self.page.evaluate('history.length')
        if not self.page.locator('#admin-other-group').evaluate('el=>el.open'):
            self.page.locator('#admin-other-group > summary').click()
        self.page.locator('#toggle-reset').click()
        self.page.locator('#reset-test').check()
        self.page.locator('#reset-ack').check()
        self.page.locator('#reset-apply').click()
        self.page.wait_for_function("!resetting&&!backingUp&&document.querySelector('#reset-preview').textContent.startsWith('選択した初期化が完了')")
        self.assertEqual(self.page.evaluate('history.length'),length)
        self.assert_changed_profile_history()
        for store in ['answers','progress','sessions','coinEvents','reviewEvents','coinSpends']:
            self.assertEqual([r for r in self.snapshot()[store] if r.get('profile')=='student'],
                             [r for r in before[store] if r.get('profile')=='student'],store)
            self.assertEqual([r for r in self.snapshot()[store] if r.get('profile')=='test'],[],store)

    def test_test_admin_full_reset_replaces_current_history_profile(self):
        self.install(mastered=True)
        self.enter_test_admin()
        length=self.page.evaluate('history.length')
        if not self.page.locator('#admin-other-group').evaluate('el=>el.open'):
            self.page.locator('#admin-other-group > summary').click()
        self.page.locator('#toggle-reset').click()
        self.page.locator('#reset-all').click()
        self.page.wait_for_function("!resetting&&!backingUp&&document.querySelector('#reset-preview').textContent.startsWith('完全初期化しました')")
        self.assertEqual(self.page.evaluate('history.length'),length)
        self.assert_changed_profile_history()
        for store in ['answers','progress','sessions','coinEvents','reviewEvents','coinSpends','arcadePlays','arcadePrizes']:
            self.assertEqual(self.snapshot()[store],[],store)

    def test_test_admin_backup_restore_replaces_current_history_profile(self):
        self.install(mastered=True)
        backup=self.snapshot()
        self.enter_test_admin()
        length=self.page.evaluate('history.length')
        self.page.evaluate("""async data=>{
          pendingRestore=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:7,data});
          await applyRestore();
        }""",backup)
        self.assertEqual(self.page.evaluate('history.length'),length)
        self.assert_changed_profile_history()
        self.assertEqual(self.snapshot(),backup)

    def select_draft_and_open_admin(self):
        self.quiz()
        self.page.locator('#choices button').nth(0).click()
        self.assertTrue(self.page.evaluate('selected.length>0&&draftSelections.size>0'))
        session=self.page.evaluate("readOne('sessions','student:E01')")
        self.page.locator('#open-admin').click()
        self.screen('admin')
        return session

    def assert_no_previous_draft(self):
        self.assertEqual(self.page.evaluate('({drafts:draftSelections.size,session:currentSession,progress:currentProgress,ready:quizReady,selected,order:optionOrder})'),
                         {'drafts':0,'session':None,'progress':None,'ready':False,'selected':[],'order':[]})

    def test_reset_clears_draft_even_when_identical_session_is_recreated(self):
        session=self.select_draft_and_open_admin()
        if not self.page.locator('#admin-other-group').evaluate('el=>el.open'):
            self.page.locator('#admin-other-group > summary').click()
        self.page.locator('#toggle-reset').click()
        self.page.locator('#reset-student').check()
        self.page.locator('#reset-ack').check()
        self.page.locator('#reset-apply').click()
        self.page.wait_for_function("!resetting&&!backingUp&&document.querySelector('#reset-preview').textContent.startsWith('選択した初期化が完了')")
        self.assert_no_previous_draft()
        self.page.evaluate('session=>writeSession(session)',session)
        self.back('quiz')
        self.assertEqual(self.page.evaluate('currentSession'),session)
        self.assertEqual(self.page.evaluate('selected'),[])
        self.assertEqual(self.page.locator('#choices button[aria-pressed="true"]').count(),0)

    def test_backup_restore_clears_draft_even_for_identical_saved_session(self):
        session=self.select_draft_and_open_admin()
        backup=self.snapshot()
        self.page.evaluate("""async data=>{
          pendingRestore=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:7,data});
          await applyRestore();
        }""",backup)
        self.assert_no_previous_draft()
        self.assertEqual(self.snapshot(),backup)
        self.back('quiz')
        self.assertEqual(self.page.evaluate('currentSession'),session)
        self.assertEqual(self.page.evaluate('selected'),[])
        self.assertEqual(self.page.locator('#choices button[aria-pressed="true"]').count(),0)
        self.assertEqual(self.snapshot(),backup)



if __name__ == '__main__':
    unittest.main()
