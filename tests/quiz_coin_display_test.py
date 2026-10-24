"""Issue #14: 問題画面の保存済み残高・競合・タッチ配置を架空データで検証。

復帰イベントの注入はSafari実機/bfcacheの検証を代替しない。
実行・準備は question_editor_test.py と同じ。
"""
import unittest

import history_navigation_test as navigation


class QuizCoinDisplayTest(unittest.TestCase):
    # Issue #13のブラウザと架空データの準備・操作を共用する。
    # TestCase自体は継承せず、既存テスト115件を重複して数えない。
    setUpClass = classmethod(navigation.HistoryNavigationTest.setUpClass.__func__)
    tearDownClass = classmethod(navigation.HistoryNavigationTest.tearDownClass.__func__)
    setUp = navigation.HistoryNavigationTest.setUp
    tearDown = navigation.HistoryNavigationTest.tearDown
    ready = navigation.HistoryNavigationTest.ready
    install = navigation.HistoryNavigationTest.install
    snapshot = navigation.HistoryNavigationTest.snapshot
    quiz = navigation.HistoryNavigationTest.quiz
    screen = navigation.HistoryNavigationTest.screen
    back = navigation.HistoryNavigationTest.back
    forward = navigation.HistoryNavigationTest.forward
    answer = navigation.HistoryNavigationTest.answer
    return_event = navigation.HistoryNavigationTest.return_event
    second_tab = navigation.HistoryNavigationTest.second_tab

    def balance(self, amount, page=None):
        page = page or self.page
        text = f'所持 {amount:,}枚'
        page.wait_for_function(
            'text=>document.querySelector("#quiz-coin-amount").textContent===text', arg=text)
        self.assertEqual(page.locator('#quiz-coin-amount').inner_text(), text)
        self.assertEqual(page.evaluate('getAvailableCoins()'), amount)

    def next_question(self):
        self.page.locator('#next').click()
        self.page.wait_for_function('quizReady&&phase==="question"')

    def hold_balance(self):
        self.page.evaluate("""()=>{
          window.originalBalance=getAvailableCoins;
          getAvailableCoins=async who=>{
            const balance=await originalBalance(who);
            await new Promise(resolve=>window.releaseBalance=resolve);
            return balance;
          };
          window.oldCoins=refreshCoinDisplay();
        }""")
        self.page.wait_for_function('typeof releaseBalance==="function"')

    def test_toolbar_is_quiz_only_and_home_coins_never_duplicate(self):
        self.assertTrue(self.page.locator('#home-coins').is_visible())
        self.assertTrue(self.page.locator('#quiz-coins').is_hidden())
        self.assertEqual(self.page.locator('header .gold-coin').count(), 0)
        self.quiz()
        self.balance(0)
        self.assertTrue(self.page.locator('#home-coins').is_hidden())
        self.assertEqual(self.page.locator('#back-home').inner_text(), '🏠 ホームへ')
        self.assertEqual(self.page.locator('.quiz-toolbar > #back-home').count(), 1)
        self.assertEqual(self.page.locator('.quiz-toolbar > #quiz-coins').count(), 1)
        self.assertEqual(self.page.locator('#quiz-coins img').get_attribute('src'),
                         'assets/coins/crown-gold.webp')
        self.page.locator('#quiz-coins img').evaluate('img=>img.decode()')
        self.assertEqual(self.page.locator('#quiz-coins').get_attribute('role'), 'status')
        self.page.locator('#back-home').click()
        self.screen('home')
        self.assertTrue(self.page.locator('#quiz-coins').is_hidden())
        self.assertEqual(self.page.locator('#home-coins:visible').count(), 1)

    def test_initial_loading_does_not_show_false_zero_or_old_profile(self):
        self.page.evaluate("""()=>{
          window.originalRead=readQuizState;
          readQuizState=async(...args)=>{
            await new Promise(resolve=>window.releaseQuiz=resolve);
            return originalRead(...args);
          };
          window.originalBalance=getAvailableCoins;
          getAvailableCoins=async who=>{
            await new Promise(resolve=>window.releaseBalance=resolve);
            return originalBalance(who);
          };
          window.openingQuiz=startEra('E01');
        }""")
        self.page.wait_for_function('typeof releaseQuiz==="function"&&typeof releaseBalance==="function"')
        self.screen('quiz')
        self.assertEqual(self.page.locator('#quiz-coin-amount').inner_text(), '確認中…')
        self.page.evaluate('async()=>{getAvailableCoins=originalBalance;readQuizState=originalRead;releaseBalance();releaseQuiz();await openingQuiz;}')
        self.balance(0)

    def test_zero_loading_error_and_recovery_are_distinct(self):
        self.quiz()
        self.balance(0)
        self.hold_balance()
        self.assertEqual(self.page.locator('#quiz-coin-amount').inner_text(), '確認中…')
        self.page.evaluate("""async()=>{
          getAvailableCoins=async()=>{throw new Error('架空の残高読込失敗');};
          await refreshCoinDisplay().catch(()=>{});
          releaseBalance();await oldCoins;
        }""")
        self.assertEqual(self.page.locator('#quiz-coin-amount').inner_text(), '確認できません')
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '確認できません')
        self.assertTrue(self.page.locator('#crane-start').is_disabled())
        self.page.evaluate('async()=>{getAvailableCoins=originalBalance;await refreshCoinDisplay();}')
        self.balance(0)
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '0')

    def test_committed_snapshot_uses_existing_single_readonly_transaction(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        result = self.page.evaluate("""async()=>{
          const original=db.transaction.bind(db),seen=[];
          db.transaction=(names,mode)=>{seen.push({names,mode});return original(names,mode);};
          try {await refreshCoinDisplay();return seen;}
          finally {db.transaction=original;}
        }""")
        self.assertEqual(result, [{'names': ['coinEvents', 'reviewEvents', 'coinSpends'], 'mode': 'readonly'}])

    def test_selection_alone_never_changes_balance_or_stores(self):
        self.quiz()
        before = self.snapshot()
        for button in self.page.locator('#choices button').all():
            button.click()
            self.balance(0)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.page.locator('#result').is_hidden())

    def test_saved_amount_is_formatted_with_thousands_separators(self):
        self.page.evaluate("""async()=>{
          const data=plushFixture();
          data.sampleSettings=SAMPLE_QUESTIONS.map(q=>({id:q.id,hidden:true}));
          data.reviewEvents.push(...Array.from({length:1000},(_,i)=>({
            ...data.reviewEvents[0],key:`grouping-${i}`
          })));
          await plushInstall(data);await navigateHome('student');
        }""")
        self.quiz()
        self.balance(2805)
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '2,805')

    def test_reward_is_displayed_only_after_answer_transaction_commits(self):
        self.quiz()
        before = self.snapshot()
        self.page.evaluate("""()=>{
          window.originalSave=saveAnswer;
          saveAnswer=async(...args)=>{
            await new Promise(resolve=>window.releaseSave=resolve);
            return originalSave(...args);
          };
          selected=[...currentQuestion.answers];updateChoices();window.answering=grade();
        }""")
        self.page.wait_for_function('typeof releaseSave==="function"')
        self.page.evaluate('refreshCoinDisplay()')
        self.balance(0)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.page.locator('#result').is_hidden())
        self.page.evaluate('async()=>{releaseSave();await answering;saveAnswer=originalSave;}')
        self.balance(2)
        self.assertIn('+2 コイン獲得！', self.page.locator('#result').inner_text())
        self.assertNotIn('所持', self.page.locator('#result').inner_text())
        self.assertNotIn('+', self.page.locator('#quiz-coins').inner_text())

    def test_correct_wrong_zero_and_mastery_review_rewards_match_saved_balance(self):
        self.quiz()
        expected = [2, 5, 7, 7, 7, 7, 9]
        for i, amount in enumerate(expected):
            if i:
                self.next_question()
                self.balance(expected[i-1])
            self.answer(correct=i != 3)
            self.balance(amount)
            earned = amount - (expected[i-1] if i else 0)
            result = self.page.locator('#result').inner_text()
            if earned:
                self.assertIn(f'+{earned} コイン獲得！', result)
            else:
                self.assertNotIn('コイン獲得', result)
            self.assertEqual(self.page.evaluate('currentProgress.mastered'), i in [1, 2, 5, 6])
        after = self.snapshot()
        self.assertEqual(len(after['answers']), 7)
        self.assertEqual(len(after['coinClaims']), 2)
        self.assertEqual(len(after['coinEvents']), 2)
        self.assertEqual(len(after['reviewEvents']), 2)

    def test_first_correct_standard_reward_is_separate_from_owned_amount(self):
        self.page.evaluate("""async()=>{
          const q={...QUESTIONS.find(q=>q.era==='E01'),difficulty:'standard'};
          const tx=db.transaction('questions','readwrite');tx.objectStore('questions').put(q);
          await new Promise(resolve=>tx.oncomplete=resolve);await loadImportedQuestions();
        }""")
        self.quiz()
        self.answer()
        self.balance(4)
        self.assertIn('+4 コイン獲得！', self.page.locator('#result').inner_text())

    def test_real_transaction_abort_does_not_add_uncommitted_reward(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        before = self.snapshot()
        self.page.evaluate("""()=>{
          window.originalAdd=IDBObjectStore.prototype.add;
          IDBObjectStore.prototype.add=function(...args){
            const req=originalAdd.apply(this,args);
            if(this.name==='answers')req.addEventListener('success',()=>this.transaction.abort());
            return req;
          };
        }""")
        self.answer()
        self.balance(805)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.page.locator('#result').is_hidden())
        self.page.evaluate('()=>{IDBObjectStore.prototype.add=originalAdd;}')
        self.return_event()
        self.balance(805)
        self.answer()
        self.balance(807)

    def test_save_rejection_keeps_balance_and_next_success_recovers(self):
        self.quiz()
        before = self.snapshot()
        self.page.evaluate("""()=>{
          window.originalSave=saveAnswer;
          saveAnswer=async()=>{throw new Error('架空の回答保存失敗');};
        }""")
        self.answer()
        self.balance(0)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.page.locator('#result').is_hidden())
        self.page.evaluate('()=>{saveAnswer=originalSave;}')
        self.answer()
        self.balance(2)

    def test_balance_read_failure_after_commit_shows_unknown_and_later_recovers(self):
        self.quiz()
        self.page.evaluate("""()=>{
          window.originalSave=saveAnswer;window.originalBalance=getAvailableCoins;
          saveAnswer=async(...args)=>{
            const saved=await originalSave(...args);
            getAvailableCoins=async()=>{throw new Error('保存後の架空読込失敗');};
            return saved;
          };
        }""")
        self.answer()
        self.assertEqual(self.page.locator('#quiz-coin-amount').inner_text(), '確認できません')
        self.assertIn('+2 コイン獲得！', self.page.locator('#result').inner_text())
        before = self.snapshot()
        self.assertEqual(len(before['answers']), 1)
        self.page.evaluate('async()=>{saveAnswer=originalSave;getAvailableCoins=originalBalance;await refreshCoinDisplay();}')
        self.balance(2)
        self.assertEqual(self.snapshot(), before)

    def test_next_question_reloads_external_spend_without_history_growth(self):
        self.install(mastered=True)
        self.quiz()
        self.answer()
        self.balance(807)
        other = self.second_tab()
        other.evaluate("purchaseCranePlay(newArcadePlay('student'))")
        self.assertEqual(self.page.locator('#quiz-coin-amount').inner_text(), '所持 807枚')
        length = self.page.evaluate('history.length')
        self.next_question()
        self.balance(707)
        self.assertEqual(self.page.evaluate('history.length'), length)

    def test_back_forward_restores_question_order_result_and_balance_without_rewards(self):
        self.quiz()
        self.answer()
        self.balance(2)
        before = self.snapshot()
        state = self.page.evaluate('({id:currentQuestion.id,order:optionOrder,selected,phase})')
        result = self.page.locator('#result').inner_text()
        length = self.page.evaluate('history.length')
        self.page.evaluate('()=>{grade=saveAnswer=()=>{throw new Error("復帰時の二重採点");};}')
        for _ in range(3):
            self.back('home')
            self.forward('quiz')
            self.balance(2)
            self.return_event()
            self.balance(2)
        self.assertEqual(self.page.evaluate('({id:currentQuestion.id,order:optionOrder,selected,phase})'), state)
        self.assertEqual(self.page.locator('#result').inner_text(), result)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('history.length'), length)

    def test_reload_restores_saved_balance_and_result_without_duplicate_reward(self):
        self.quiz()
        self.answer()
        self.balance(2)
        before = self.snapshot()
        self.page.reload()
        self.ready()
        self.balance(2)
        self.assertIn('+2 コイン獲得！', self.page.locator('#result').inner_text())
        self.assertEqual(self.snapshot(), before)

    def test_other_screen_return_reads_latest_balance(self):
        self.install(mastered=True)
        self.quiz()
        self.page.locator('#open-admin').click()
        self.screen('admin')
        other = self.second_tab()
        other.evaluate("purchaseCranePlay(newArcadePlay('student'))")
        before = self.snapshot()
        self.back('quiz')
        self.balance(705)
        self.assertEqual(self.snapshot(), before)

    def test_other_tab_spend_is_reflected_on_bfcache_visibility_and_window_focus(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        other = self.second_tab()
        for trigger, amount in [('pageshow', 705), ('visibility', 605), ('focus', 505)]:
            with self.subTest(trigger=trigger):
                other.evaluate("""async()=>{
                  const play=await purchaseCranePlay(newArcadePlay('student'));
                  play.armX=0;
                  await commitCraneOutcome(play,chooseCraneOutcome(play,()=>.99));
                  await finishCranePlay(play.id);
                }""")
                before = self.snapshot()
                if trigger == 'pageshow':
                    self.page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
                    self.return_event()
                elif trigger == 'visibility':
                    self.page.evaluate("""async()=>{
                      const original=reconcilePage;
                      try {
                        reconcilePage=(...args)=>window.visibilityRestoration=original(...args);
                        Object.defineProperty(document,'hidden',{configurable:true,value:true});
                        document.dispatchEvent(new Event('visibilitychange'));
                        Object.defineProperty(document,'hidden',{configurable:true,value:false});
                        document.dispatchEvent(new Event('visibilitychange'));
                        // show()の先行取得だけでなく、復帰の最終取得まで待って照合する。
                        await visibilityRestoration;
                      } finally {reconcilePage=original;delete document.hidden;}
                    }""")
                else:
                    self.page.evaluate("dispatchEvent(new Event('focus'))")
                self.balance(amount)
                self.assertEqual(self.snapshot(), before)

    def test_other_tab_answer_is_reflected_on_return_without_regrading(self):
        self.quiz()
        other = self.second_tab()
        self.quiz(page=other)
        self.answer(page=other)
        self.balance(2, other)
        before = self.snapshot()
        self.return_event()
        self.balance(2)
        self.assertEqual(self.page.evaluate('phase'), 'result')
        self.assertEqual(self.snapshot(), before)

    def test_student_test_and_history_use_each_profiles_saved_balance(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        self.page.evaluate("async()=>{await navigateHome('test');await startEra('E01');}")
        self.balance(9)
        self.answer()
        self.balance(11)
        self.back('home')
        self.back('quiz')
        self.balance(805)
        self.forward('home')
        self.forward('quiz')
        self.balance(11)

    def test_late_success_cannot_overwrite_another_profiles_balance(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        self.hold_balance()
        self.page.evaluate("""async()=>{
          getAvailableCoins=originalBalance;await navigateHome('test');await startEra('E01');
          releaseBalance();await oldCoins;
        }""")
        self.balance(9)

    def test_late_error_cannot_overwrite_new_profile_or_disable_new_arcade(self):
        self.quiz()
        self.page.evaluate("""()=>{
          window.originalBalance=getAvailableCoins;
          getAvailableCoins=async()=>{
            await new Promise(resolve=>window.releaseBalance=resolve);
            throw new Error('古い要求の架空エラー');
          };
          window.oldCoins=refreshCoinDisplay().catch(()=>{});
        }""")
        self.page.wait_for_function('typeof releaseBalance==="function"')
        self.page.evaluate("""async()=>{
          getAvailableCoins=originalBalance;await navigateHome('test');await openArcade();
          releaseBalance();await oldCoins;
        }""")
        self.assertEqual(self.page.locator('#arcade-balance').inner_text(), '∞（無料）')
        self.assertFalse(self.page.locator('#crane-start').is_disabled())
        self.page.evaluate("startEra('E01')")
        self.balance(0)

    def test_older_request_cannot_overwrite_newer_balance_in_same_view(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        self.hold_balance()
        other = self.second_tab()
        other.evaluate("purchaseCranePlay(newArcadePlay('student'))")
        self.page.evaluate('async()=>{getAvailableCoins=originalBalance;await refreshCoinDisplay();releaseBalance();await oldCoins;}')
        self.balance(705)

    def test_old_view_cannot_overwrite_new_view_of_same_profile(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        self.hold_balance()
        self.page.evaluate('()=>{getAvailableCoins=originalBalance;}')
        self.page.evaluate('navigateHome()')
        other = self.second_tab()
        other.evaluate("purchaseCranePlay(newArcadePlay('student'))")
        self.page.evaluate("startEra('E01')")
        self.balance(705)
        self.page.evaluate('async()=>{releaseBalance();await oldCoins;}')
        self.balance(705)

    def test_loading_read_failure_replaces_stale_positive_amount_then_recovers(self):
        self.install(mastered=True)
        self.quiz()
        self.balance(805)
        self.hold_balance()
        self.assertEqual(self.page.locator('#quiz-coin-amount').inner_text(), '確認中…')
        self.page.evaluate("""async()=>{
          getAvailableCoins=async()=>{throw new Error('架空の読込失敗');};
          await refreshCoinDisplay().catch(()=>{});releaseBalance();await oldCoins;
        }""")
        self.assertEqual(self.page.locator('#quiz-coin-amount').inner_text(), '確認できません')
        self.page.evaluate('async()=>{getAvailableCoins=originalBalance;await refreshCoinDisplay();}')
        self.balance(805)

    def test_ui_refresh_navigation_and_popup_preserve_all_fourteen_stores(self):
        self.page.evaluate("""async()=>{
          const data=plushFixture(['shiba'],'student');
          data.sampleSettings=SAMPLE_QUESTIONS.map(q=>({id:q.id,hidden:true}));
          await plushInstall(data);await navigateHome('student');
        }""")
        self.quiz()
        self.balance(705)
        before = self.snapshot()
        self.assertEqual(len(before), 14)
        self.assertTrue(all(before.values()))
        self.assertEqual(self.page.evaluate('[DB_VERSION,BACKUP_VERSION,db.objectStoreNames.length]'), [7, 7, 14])
        for _ in range(3):
            self.page.evaluate('refreshCoinDisplay()')
            self.return_event()
            self.balance(705)
        self.page.locator('#back-home').click()
        self.screen('home')
        self.page.evaluate('openArcade()')
        self.page.locator('button.plush-item[data-prize-id="shiba"]').click()
        self.page.wait_for_function('document.querySelector("#plush-detail-dialog").open')
        self.page.locator('#plush-detail-close').click()
        self.back('home')
        self.back('quiz')
        self.balance(705)
        self.assertEqual(self.snapshot(), before)

    def test_home_button_uses_navigate_home_and_does_not_repeat_history_entries(self):
        self.quiz()
        self.balance(0)
        self.page.evaluate("""()=>{
          window.homeCalls=0;window.originalHome=navigateHome;
          navigateHome=(...args)=>{homeCalls++;return originalHome(...args);};
        }""")
        before = self.snapshot()
        self.page.locator('#back-home').click()
        self.screen('home')
        self.assertEqual(self.page.evaluate('homeCalls'), 1)
        self.assertEqual(self.page.url, self.url)
        length = self.page.evaluate('history.length')
        self.page.evaluate('navigateHome()')
        self.assertEqual(self.page.evaluate('history.length'), length)
        self.back('quiz')
        self.forward('home')
        self.assertEqual(self.snapshot(), before)

    def test_iphone_ipad_toolbar_long_questions_two_to_six_choices_fit(self):
        self.quiz()
        self.balance(0)
        for width, height in [(375, 812), (390, 844), (768, 1024), (1024, 768), (320, 568)]:
            for count in [2, 3, 4, 5, 6]:
                with self.subTest(width=width, count=count):
                    self.page.set_viewport_size({'width': width, 'height': height})
                    self.page.evaluate(r"""count=>{
                      currentQuestion={...currentQuestion,q:'架空の長い問題文です。\n'+('確認する文章です。'.repeat(20)),
                        options:Array.from({length:count},(_,i)=>`架空の選択肢${i}\n続きの文章です。`),answers:count===2?[0]:[0,1]};
                      optionOrder=Array.from({length:count},(_,i)=>i);selected=[];renderQuestion();
                    }""", count)
                    self.balance(0)
                    self.assertTrue(self.page.locator('#question-text').evaluate(
                        'el=>getComputedStyle(el).whiteSpace==="pre-wrap"'))
                    for label in ['所持 0枚', '所持 1,234,567枚', '所持 9,007,199,254,740,991枚', '確認中…', '確認できません']:
                        self.page.locator('#quiz-coin-amount').evaluate('(el,text)=>el.textContent=text', label)
                        self.assertTrue(self.page.evaluate("""()=>{
                          const home=document.querySelector('#back-home').getBoundingClientRect();
                          const coins=document.querySelector('#quiz-coins').getBoundingClientRect();
                          const elements=['#back-home','#quiz-coins','#quiz-coin-amount','#question-text','#check',...Array.from({length:document.querySelectorAll('#choices button').length},(_,i)=>`#choices button:nth-child(${i+1})`)];
                          return document.documentElement.scrollWidth<=innerWidth&&
                            home.width>=44&&home.height>=44&&home.right<=coins.left&&
                            Math.abs((home.top+home.bottom)/2-(coins.top+coins.bottom)/2)<1&&
                            elements.every(selector=>{
                              const el=document.querySelector(selector),r=el.getBoundingClientRect();
                              return r.width>0&&r.left>=0&&r.right<=innerWidth&&el.scrollWidth<=el.clientWidth+1;
                            })&&[...document.querySelectorAll('#choices button')].every(b=>b.getBoundingClientRect().height>=44);
                        }"""), (width, count, label))
                    self.page.locator('#choices button').nth(0).click()
                    if count > 2:
                        self.page.locator('#choices button').nth(1).click()
                    self.assertFalse(self.page.locator('#check').is_disabled())
                    self.page.evaluate('refreshCoinDisplay()')
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.evaluate('reconcilePage()')
        self.answer()
        self.balance(2)
        self.assertTrue(self.page.locator('#next').is_visible())
