"""新学習モード: 教材と無関係な架空問題で保存・抽選・競合・互換性を検証。"""
import unittest
import history_navigation_test as navigation
from plush_test import FIXTURE_HELPERS


class StudyModesTest(unittest.TestCase):
    setUpClass = classmethod(navigation.HistoryNavigationTest.setUpClass.__func__)
    tearDownClass = classmethod(navigation.HistoryNavigationTest.tearDownClass.__func__)
    ready = navigation.HistoryNavigationTest.ready
    screen = navigation.HistoryNavigationTest.screen
    snapshot = navigation.HistoryNavigationTest.snapshot
    second_tab = navigation.HistoryNavigationTest.second_tab
    return_event = navigation.HistoryNavigationTest.return_event

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.dialog_handler = lambda dialog: dialog.accept('初期化') if dialog.type == 'prompt' else dialog.accept()
        self.page.on('dialog', self.dialog_handler)
        self.page.goto(self.url)
        self.ready()
        self.page.evaluate(FIXTURE_HELPERS)
        self.install()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def install(self, count=16, weak=12):
        self.page.evaluate("""async ({count,weak})=>{
          const data=plushFixture();
          for(const name of BACKUP_STORES)data[name]=[];
          data.sampleSettings=SAMPLE_QUESTIONS.map(q=>({id:q.id,hidden:true}));
          data.coinMeta=[{id:COIN_MIGRATION_KEY,migratedAt:'2020-01-01T00:00:00.000Z',legacyClaims:0}];
          const tags=Object.keys(GENRE_TAGS);
          for(let i=0;i<count;i++) {
            const q={id:`FAKE-STUDY-${String(i).padStart(3,'0')}`,era:ERAS[i%10][0],
              q:`架空の動作確認 ${i}\\n正しい記号を選ぼう。`,options:['記号の甲','記号の乙','記号の丙'],
              answers:i%2?[0,2]:[0],why:'教材に由来しないテスト用の解説です。',
              revision:1,difficulty:'basic',tag:tags[i%5],shuffleOptions:true,deleted:false};
            data.questions.push(q);
            if(i<weak)data.progress.push({key:`student:${q.id}`,profile:'student',questionId:q.id,revision:1,
              attempts:1,streak:0,mastered:false,everWrong:true,lastAnsweredAt:'2020-01-01T00:00:00.000Z'});
          }
          await plushInstall(data);await ensureArcadeBoards();await navigateHome('student');
        }""", {'count': count, 'weak': weak})

    def start(self, mode='weak', genre=None, page=None):
        page = page or self.page
        page.evaluate('({mode,genre})=>startStudy(mode,genre)', {'mode': mode, 'genre': genre})
        page.wait_for_function('quizReady||phase==="complete"')

    def answer(self, correct=True, page=None):
        page = page or self.page
        page.evaluate('correct=>{selected=correct?[...currentQuestion.answers]:[1];updateChoices();}', correct)
        page.evaluate('grade()')
        page.wait_for_function('!saving&&(quizReady||phase==="complete")')

    def next(self):
        self.page.evaluate('nextStudy()')

    def test_weak_current_revision_and_state_filter(self):
        self.page.evaluate("""async()=>{
          const p=await readAll('progress');
          p[0]={...p[0],streak:2,mastered:true};p[1].revision=2;
          p[2].everWrong=false;
          const tx=db.transaction(['progress','questions'],'readwrite');
          p.forEach(x=>tx.objectStore('progress').put(x));
          tx.objectStore('questions').put({...QUESTIONS[3],deleted:true});
          await new Promise((r,j)=>{tx.oncomplete=r;tx.onerror=j;});await reconcilePage();
        }""")
        self.start()
        entries=self.page.evaluate('currentSession.entries.map(e=>e.questionId)')
        self.assertEqual(len(entries), 8)
        self.assertTrue(all(int(q.rsplit('-', 1)[1]) in range(4, 12) for q in entries))
        self.assertEqual(len(entries), len(set(entries)))

    def test_ten_unique_frozen_entries_and_result_denominator(self):
        self.start()
        original = self.page.evaluate('currentSession.entries')
        ids=[]
        for i in range(10):
            ids.append(self.page.evaluate('currentQuestion.id'))
            self.answer(i % 2 == 0)
            self.assertEqual(self.page.evaluate('currentSession.entries'), original)
            if i == 9:
                self.assertIn('回答数 10問', self.page.locator('#study-result-summary').inner_text())
            self.next()
        self.screen('study-finished')
        self.assertEqual(len(set(ids)), 10)
        self.assertIn('回答数 10問 ｜ 正解数 5問 ｜ 正答率 50%', self.page.locator('#study-result-summary').inner_text())
        self.assertEqual(len(self.snapshot()['answers']), 10)
        self.assertEqual(self.page.evaluate('currentSession.entries'), original)

    def test_one_to_nine_and_empty_modes(self):
        for n in [1, 3, 9]:
            self.install(n, n)
            self.start()
            for _ in range(n):
                self.answer()
                self.next()
            self.assertEqual(self.page.evaluate('phase'), 'complete')
            self.assertEqual(self.page.evaluate('currentSession.results.length'), n)
        self.install(0, 0)
        self.assertTrue(self.page.locator('#start-weak').is_disabled())
        self.assertIn('苦手問題はありません', self.page.locator('#weak-count').inner_text())
        self.assertEqual(self.page.locator('#genre-list button:disabled').count(), 5)
        self.start('genre', 'culture')
        self.screen('study-finished')
        self.assertIn('回答数 0問', self.page.locator('#study-result-summary').inner_text())

    def test_all_five_genres_cross_eras_including_mastered_and_unseen(self):
        self.page.evaluate("""async()=>{
          const tx=db.transaction('progress','readwrite');
          tx.objectStore('progress').clear();
          for(const q of QUESTIONS.slice(0,5))tx.objectStore('progress').put({key:`student:${q.id}`,profile:'student',questionId:q.id,revision:1,attempts:2,streak:2,mastered:true,everWrong:true,lastAnsweredAt:'2020-01-01'});
          await new Promise(r=>tx.oncomplete=r);await navigateHome();
        }""")
        for tag in ['person', 'politics', 'culture', 'society', 'war_diplomacy']:
            self.start('genre', tag)
            qs=self.page.evaluate('currentSession.entries.map(e=>QUESTIONS.find(q=>q.id===e.questionId))')
            self.assertTrue(all(q['tag'] == tag for q in qs))
            self.assertGreaterEqual(len(set(q['era'] for q in qs)), 2)
            self.assertIn(tag, self.page.evaluate('currentSession.key'))
            self.page.evaluate('navigateHome()')
        self.assertEqual(len(self.snapshot()['studySets']), 5)

    def test_tag_unset_deleted_and_hidden_samples_excluded(self):
        self.page.evaluate("""async()=>{
          const tx=db.transaction('questions','readwrite');
          for(const q of QUESTIONS.filter(q=>q.tag==='person')) {
            const copy={...q};if(q.id.endsWith('000'))delete copy.tag;else copy.deleted=true;
            tx.objectStore('questions').put(copy);
          }
          await new Promise(r=>tx.oncomplete=r);await reconcilePage();
        }""")
        self.assertTrue(self.page.locator('[data-study-genre="person"]').is_disabled())
        self.start('genre', 'person')
        self.assertEqual(self.page.evaluate('currentSession.entries'), [])

    def test_two_correct_shared_mastery_and_wrong_returns_to_weak(self):
        self.install(1, 1)
        self.start()
        self.answer()
        self.next()
        self.start('genre', 'person')
        self.answer()
        self.next()
        self.assertTrue(self.snapshot()['progress'][0]['mastered'])
        self.start()
        self.assertEqual(self.page.evaluate('phase'), 'complete')
        self.assertIn('苦手問題をすべて克服', self.page.locator('#study-result-remaining').inner_text())
        self.start('genre', 'person')
        self.answer(False)
        self.next()
        self.start()
        self.assertEqual(self.page.evaluate('currentSession.entries.length'), 1)
        self.assertEqual(self.page.evaluate('phase'), 'question')

    def test_independent_resume_selection_reload_result_and_profiles(self):
        self.start()
        self.page.locator('#choices button').first.click()
        self.page.evaluate('pendingSelection')
        weak=self.page.evaluate('currentSession')
        self.page.evaluate('navigateHome()')
        self.start('genre', 'culture')
        self.answer()
        genre=self.page.evaluate('currentSession')
        self.page.evaluate('navigateHome()')
        self.start()
        self.assertEqual(self.page.evaluate('currentSession'), weak)
        self.page.reload()
        self.ready()
        self.assertEqual(self.page.evaluate('currentSession'), weak)
        self.page.evaluate('navigateHome()')
        self.start('genre', 'culture')
        self.assertEqual(self.page.evaluate('currentSession'), genre)
        before=self.snapshot()
        self.page.go_back()
        self.screen('home')
        self.page.go_forward()
        self.page.wait_for_function('quizReady')
        self.return_event()
        self.assertEqual(self.snapshot(), before)
        self.page.evaluate('navigateHome("test")')
        self.start('genre', 'culture')
        self.answer()
        now=self.snapshot()
        self.assertEqual([a for a in now['answers'] if a['profile']=='student'], before['answers'])
        self.assertEqual(len([s for s in now['studySets'] if s['profile']=='test']), 1)
        self.assertEqual(now['sessions'], [])

    def test_skips_revised_deleted_and_newly_mastered_without_refill(self):
        self.install(6, 6)
        self.start()
        self.answer()
        self.page.evaluate("""async()=>{
          const tx=db.transaction(['questions','progress'],'readwrite');
          for(const [i,e] of currentSession.entries.entries()) {
            if(i===0)continue;
            const q=QUESTIONS.find(q=>q.id===e.questionId);
            if(i===1)tx.objectStore('questions').put({...q,revision:2});
            else if(i===2)tx.objectStore('questions').put({...q,deleted:true});
            else tx.objectStore('progress').put({key:`student:${q.id}`,profile:'student',questionId:q.id,revision:1,attempts:3,streak:2,mastered:true,everWrong:true,lastAnsweredAt:'2020-01-01'});
          }
          await new Promise(r=>tx.oncomplete=r);
        }""")
        self.next()
        self.screen('study-finished')
        self.assertIn('回答数 1問 ｜ 正解数 1問 ｜ 正答率 100%', self.page.locator('#study-result-summary').inner_text())
        self.assertEqual(self.page.evaluate('currentSession.entries.length'), 6)
        self.assertEqual(len(self.snapshot()['answers']), 1)

    def test_restart_confirmation_keeps_history_rewards_and_other_modes(self):
        self.start('genre', 'culture')
        self.answer()
        self.start()
        self.answer()
        before=self.snapshot()
        self.page.remove_listener('dialog', self.dialog_handler)
        dismiss = lambda d:d.dismiss()
        self.page.on('dialog', dismiss)
        self.page.evaluate('startStudy("weak",null,true)')
        self.assertEqual(self.snapshot(), before)
        self.page.remove_listener('dialog', dismiss)
        self.page.on('dialog', self.dialog_handler)
        self.page.evaluate('startStudy("weak",null,true)')
        after=self.snapshot()
        for store in ['answers','progress','coinClaims','coinEvents','sessions']:
            self.assertEqual(after[store], before[store])
        self.assertEqual([s for s in after['studySets'] if s['mode']=='genre'], [s for s in before['studySets'] if s['mode']=='genre'])
        self.assertNotEqual(self.page.evaluate('currentSession.setId'), next(s['setId'] for s in before['studySets'] if s['mode']=='weak'))

    def test_two_tabs_same_answer_and_stale_next_commit_once(self):
        self.start()
        other=self.second_tab()
        self.start(page=other)
        for page in [self.page,other]:
            page.evaluate('selected=[...currentQuestion.answers];updateChoices()')
        self.page.evaluate('window.firstSave=grade()')
        other.evaluate('grade()')
        self.page.evaluate('window.firstSave')
        self.assertEqual(len(self.snapshot()['answers']), 1)
        self.assertEqual(self.page.evaluate('currentSession.results.length'), 1)
        self.next()
        current=self.snapshot()['studySets']
        other.evaluate('nextStudy()')
        self.assertEqual(self.snapshot()['studySets'], current)
        self.assertEqual(self.page.evaluate('currentQuestion.id'), other.evaluate('currentQuestion.id'))

    def test_answer_abort_rolls_back_all_stores_and_can_retry(self):
        self.start()
        before=self.snapshot()
        self.page.evaluate("""()=>{
          window.originalAdd=IDBObjectStore.prototype.add;
          IDBObjectStore.prototype.add=function(value,...args){
            if(this.name==='answers'){const req=originalAdd.call(this,value,...args);this.transaction.abort();return req;}
            return originalAdd.call(this,value,...args);
          };
        }""")
        self.answer()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('phase'), 'question')
        self.page.evaluate('()=>{IDBObjectStore.prototype.add=originalAdd;}')
        self.answer()
        self.assertEqual(len(self.snapshot()['answers']), 1)

    def test_stale_question_at_submit_never_records_answer(self):
        self.start()
        self.page.evaluate("""async()=>{
          const tx=db.transaction('questions','readwrite');tx.objectStore('questions').put({...currentQuestion,revision:2});
          await new Promise(r=>tx.oncomplete=r);
        }""")
        old=self.page.evaluate('currentQuestion.id')
        self.answer()
        self.assertEqual(len(self.snapshot()['answers']), 0)
        self.assertNotEqual(self.page.evaluate('currentQuestion.id'), old)

    def test_v9_roundtrip_and_v1_to_v8_discard_only_sets(self):
        self.start()
        self.answer()
        self.page.evaluate('nextStudy()')
        self.start('genre', 'culture')
        before=self.snapshot()
        self.assertEqual(self.page.evaluate('BACKUP_VERSION'), 9)
        self.page.evaluate("""async()=>{
          const data=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:9,data:await snapshotAllStores()});
          await replaceAllStores(data);await reconcilePage();
        }""")
        self.assertEqual(self.snapshot(), before)
        for version in range(1,9):
            out=self.page.evaluate("""async version=>{
              const data=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:version,data:await snapshotAllStores()});
              return {sets:data.studySets,questions:data.questions.length,progress:data.progress.length};
            }""",version)
            self.assertEqual(out['sets'], [])
            self.assertEqual(out['questions'], 16)
            self.assertEqual(out['progress'], 12)
        self.page.evaluate("""async()=>{
          const data=validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:8,data:await snapshotAllStores()});
          await replaceAllStores(data);
        }""")
        after=self.snapshot()
        self.assertEqual(after['studySets'], [])
        for store in ['progress','questions','answers','coinEvents']:
            self.assertEqual(before[store], after[store])

    def test_v9_validation_rejects_corrupt_progress_without_writing(self):
        self.start()
        before=self.snapshot()
        for mutation in ['s.entries.push(s.entries[0])','s.position=99','s.results=[{position:0}]','s.profile="other"','s.optionOrder=[0,0]']:
            message=self.page.evaluate("""async mutation=>{
              const data=await snapshotAllStores(),s=data.studySets[0];eval(mutation);
              try{validateBackup({backupFormat:BACKUP_FORMAT,backupVersion:9,data});return null;}catch(e){return e.message;}
            }""", mutation)
            self.assertIsNotNone(message)
        self.assertEqual(self.snapshot(), before)

    def test_reset_profile_and_full_reset_include_study_sets(self):
        self.start('genre', 'culture')
        self.page.evaluate('navigateHome("test")')
        self.start('genre', 'culture')
        self.page.evaluate('navigate("admin")')
        self.page.evaluate("""async()=>{
          for(const id of RESET_CHOICES)$(id).checked=false;
          $('reset-test').checked=true;$('reset-ack').checked=true;await updateResetPreview();await applySelectedReset();
        }""")
        sets=self.snapshot()['studySets']
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]['profile'], 'student')
        self.page.evaluate('applyFullReset()')
        self.assertEqual(self.snapshot()['studySets'], [])

    def test_responsive_touch_and_rotation_preserve_set(self):
        self.start()
        before=self.snapshot()
        for width,height in [(390,844),(844,390),(768,1024),(1024,768)]:
            self.page.set_viewport_size({'width':width,'height':height})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            for selector in ['#back-home','#restart-study','#choices button']:
                self.assertGreaterEqual(self.page.locator(selector).first.bounding_box()['height'],44)
        self.assertEqual(self.snapshot(), before)

    def test_card_and_rewards_share_atomic_commit_with_final_answer(self):
        self.install(50, 50)
        self.page.evaluate("""async()=>{
          const tx=db.transaction(['questions','progress'],'readwrite');
          for(const [i,q] of QUESTIONS.entries()) {
            tx.objectStore('questions').put({...q,era:'E01'});
            tx.objectStore('progress').put({key:`student:${q.id}`,profile:'student',questionId:q.id,revision:1,
              attempts:3,streak:i?2:1,mastered:!!i,everWrong:true,lastAnsweredAt:'2020-01-01'});
          }
          await new Promise(r=>tx.oncomplete=r);await reconcilePage();
        }""")
        self.start()
        self.assertEqual(self.page.evaluate('currentSession.entries.length'), 1)
        self.answer()
        self.screen('study-finished')
        state=self.snapshot()
        self.assertEqual(len(state['awards']), 1)
        self.assertEqual(state['awards'][0]['questionCountAtEarn'], 50)
        self.assertEqual(len(state['answers']), 1)
        self.assertEqual(sum(e['amount'] for e in state['coinEvents']), 5)
        self.assertEqual(state['studySets'][0]['phase'], 'complete')
        self.assertIn('時代完全制覇', self.page.locator('#study-last-result').inner_text())
        self.page.reload()
        self.ready()
        self.assertEqual(self.snapshot(), state)
        self.assertIn('正解', self.page.locator('#study-last-result').inner_text())

    def test_final_explanation_feedback_and_complete_resume(self):
        self.install(1, 1)
        self.start()
        self.answer()
        self.screen('study-finished')
        self.assertIn('テスト用の解説', self.page.locator('#study-last-result').inner_text())
        before=self.snapshot()
        self.page.locator('#study-report-question').click()
        self.page.locator('#feedback-comment').fill('架空の指摘です')
        self.page.locator('#feedback-save').click()
        self.page.wait_for_function('!feedbackSaving&&!document.querySelector("#feedback-dialog").open')
        after=self.snapshot()
        self.assertEqual(len(after['questionFeedback']),1)
        for name in before:
            if name!='questionFeedback':self.assertEqual(before[name],after[name])
        self.return_event()
        self.page.reload()
        self.ready()
        self.screen('study-finished')
        self.assertEqual(self.snapshot(),after)

    def test_v8_upgrade_adds_only_new_store_and_is_repeatable(self):
        import subprocess
        source=subprocess.check_output(['git','show','2d3fc7b7ad48c9ae87847836ab5af81b15a578cc:index.html'],text=True)
        context=self.browser.new_context()
        page=context.new_page()
        page.route(self.url,lambda route:route.fulfill(body=source,content_type='text/html'))
        page.goto(self.url)
        self.ready(page)
        page.evaluate(FIXTURE_HELPERS)
        page.evaluate('async()=>{await plushInstall(plushFixture());}')
        before=self.snapshot(page)
        self.assertEqual(page.evaluate('[db.version,db.objectStoreNames.length]'),[8,15])
        page.unroute(self.url)
        page.reload()
        self.ready(page)
        self.assertEqual(page.evaluate('[db.version,db.objectStoreNames.length]'),[9,16])
        after=self.snapshot(page)
        for name in before:self.assertEqual(before[name],after[name])
        self.assertEqual(after['studySets'],[])
        page.reload()
        self.ready(page)
        self.assertEqual(self.snapshot(page),after)
        context.close()

    def test_old_restore_preview_explicitly_warns_sets_are_discarded(self):
        import json
        self.start()
        data=self.snapshot()
        self.page.evaluate('navigate("admin")')
        self.page.locator('#admin-backup-group > summary').click()
        self.page.locator('#toggle-backup').click()
        self.page.locator('#backup-file').set_input_files({
            'name':'synthetic-v8.json','mimeType':'application/json',
            'buffer':json.dumps({'backupFormat':'history-master-backup','backupVersion':8,'data':data}).encode()})
        self.page.wait_for_function('pendingRestore!==null')
        self.assertIn('途中セットを破棄',self.page.locator('#backup-preview').inner_text())
        self.assertEqual(self.snapshot(),data)

    def test_weighted_sampling_uses_current_revision_and_profile_history(self):
        result=self.page.evaluate("""()=>{
          const candidates=Array.from({length:30},(_,i)=>({...QUESTIONS[0],id:`FAKE-WEIGHT-${i}`}));
          const events=[];
          candidates.forEach((q,i)=>{
            if(i%3===0)return; // 未挑戦
            for(let n=0;n<20;n++)events.push({profile:'student',questionId:q.id,revision:1,correct:i%3===2});
            // 他プロフィール/旧改訂は重みに影響しない。
            for(let n=0;n<30;n++)events.push({profile:'test',questionId:q.id,revision:1,correct:false},{profile:'student',questionId:q.id,revision:2,correct:false});
          });
          const saved=Math.random,counts=[0,0,0];let seed=42;
          Math.random=()=>((seed=(1664525*seed+1013904223)>>>0)/4294967296);
          try {
            for(let n=0;n<400;n++)for(const e of sampleStudyEntries(candidates,events,'student'))counts[Number(e.questionId.split('-').pop())%3]++;
          }finally{Math.random=saved;}
          return counts;
        }""")
        self.assertGreater(result[0],result[1])
        self.assertGreater(result[1],result[2]*2)
