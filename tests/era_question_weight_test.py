"""Issue #52: 架空問題と固定乱数で時代別抽選・保存・習得の回帰を検証。

実行: PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'era_question_weight_test.py' -v
ブラウザ/サーバーと保存スナップショットは既存テストの仕組みを使用する。
"""
import unittest

import history_navigation_test as navigation
from plush_test import FIXTURE_HELPERS


# いずれも4回答中2正解で従来重みは3。回答順だけで習得状態が異なる。
STATES = {
    0: {'answers': [True, True, False, False]},
    1: {'answers': [True, False, False, True]},
    2: {'answers': [False, False, True, True]},
}


class EraQuestionWeightTest(unittest.TestCase):
    setUpClass = classmethod(navigation.HistoryNavigationTest.setUpClass.__func__)
    tearDownClass = classmethod(navigation.HistoryNavigationTest.tearDownClass.__func__)
    tearDown = navigation.HistoryNavigationTest.tearDown
    ready = navigation.HistoryNavigationTest.ready
    snapshot = navigation.HistoryNavigationTest.snapshot
    answer = navigation.HistoryNavigationTest.answer
    return_event = navigation.HistoryNavigationTest.return_event

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto(self.url)
        self.ready()
        self.page.evaluate(FIXTURE_HELPERS)
        self.seed([{'student': STATES[0]}, {'student': STATES[2]}])

    @staticmethod
    def qid(index):
        return f'FAKE-WEIGHT-{index:03}'

    def seed(self, specs):
        self.page.evaluate("""async specs=>{
          const data=Object.fromEntries(BACKUP_STORES.map(name=>[name,[]]));
          const at='2020-01-01T00:00:00.000Z';
          data.sampleSettings=SAMPLE_QUESTIONS.map(q=>({id:q.id,hidden:true}));
          data.coinMeta=[{id:COIN_MIGRATION_KEY,migratedAt:at,legacyClaims:0}];
          for(const [i,spec] of specs.entries()) {
            const q={id:`FAKE-WEIGHT-${String(i).padStart(3,'0')}`,era:spec.era||'E01',
              q:`教材と無関係な架空の記号テスト ${i}`,options:['記号の甲','記号の乙'],
              answers:[0],why:'動作確認専用の説明です。',revision:spec.revision||1,
              difficulty:'basic',tag:'culture',shuffleOptions:false,deleted:!!spec.deleted};
            data.questions.push(q);
            for(const who of ['student','test']) {
              const state=spec[who];
              if(!state)continue;
              const outcomes=state.answers||[],revision=state.revision||q.revision;
              let streak=0;
              for(const correct of [...outcomes].reverse()) {if(!correct)break;streak++;}
              for(const correct of outcomes)data.answers.push({id:data.answers.length+1,
                profile:who,questionId:q.id,revision,correct,selected:[correct?0:1],at});
              if(outcomes.length&&state.progress!==false)data.progress.push({
                key:`${who}:${q.id}`,profile:who,questionId:q.id,
                revision:state.progressRevision||revision,attempts:outcomes.length,
                streak,mastered:streak>=2,everWrong:outcomes.includes(false),lastAnsweredAt:at});
            }
          }
          await plushInstall(data);await ensureArcadeBoards();await navigateHome('student');
        }""", specs)

    def draws(self, rolls, who='student', recent=(), previous=None):
        # 抽選以外の乱数には影響を残さず、各プロフィールの保存済み進捗を渡す。
        return self.page.evaluate("""async ({rolls,who,recent,previous})=>{
          const all=await readAll('progress');
          const records=new Map(all.filter(p=>p.profile===who).map(p=>[p.questionId,p]));
          const random=Math.random,priorProfile=profile;
          try {
            profile=who;
            return rolls.map(roll=>{
              Math.random=()=>roll;
              return pickQuestion('E01',records,previous,recent)?.id||null;
            });
          } finally {Math.random=random;profile=priorProfile;}
        }""", dict(rolls=rolls, who=who, recent=list(recent), previous=previous))

    def boundary(self, weight, other_weight=3):
        boundary = weight / (weight + other_weight)
        self.assertEqual(self.draws([0, boundary - 1e-10, boundary + 1e-10, 1 - 1e-10]),
                         [self.qid(0), self.qid(0), self.qid(1), self.qid(1)])

    def begin(self, roll=0):
        self.page.evaluate("""async roll=>{
          const random=Math.random;
          try {Math.random=()=>roll;await startEra('E01');}
          finally {Math.random=random;}
        }""", roll)
        self.page.wait_for_function('quizReady')

    def next_question(self, roll=0):
        self.page.evaluate("""async roll=>{
          const random=Math.random;
          try {Math.random=()=>roll;await advance('E01',currentQuestion.id);}
          finally {Math.random=random;}
        }""", roll)
        self.page.wait_for_function('quizReady&&phase==="question"')

    def test_legacy_accuracy_formula_is_unchanged(self):
        weights = self.page.evaluate("""[
          questionWeight(),questionWeight({attempts:0,correct:0}),
          questionWeight({attempts:4,correct:0}),questionWeight({attempts:4,correct:2}),
          questionWeight({attempts:4,correct:4})]""")
        for actual, expected in zip(weights, [5, 5, 13 / 3, 3, 5 / 3]):
            self.assertAlmostEqual(actual, expected)

    def test_exact_multipliers_at_reproducible_draw_boundaries(self):
        cases = [
            ('unanswered', None, 50),
            ('no_progress_with_answers', {**STATES[0], 'progress': False}, 30),
            ('streak_zero', STATES[0], 30),
            ('streak_one', STATES[1], 30),
            ('mastered_two', STATES[2], 3),
            ('mastered_three', {'answers': [False, False, False, True, True, True]}, 3),
        ]
        for name, state, weight in cases:
            with self.subTest(state=name):
                self.seed([{'student': state}, {'student': STATES[2]}])
                self.boundary(weight)
        # 重み30と3では roll=10/11 が後者の区間の開始点。
        self.seed([{'student': STATES[0]}, {'student': STATES[2]}])
        self.assertEqual(self.draws([10 / 11]), [self.qid(1)])

    def test_accuracy_still_changes_weights_within_each_mastery_group(self):
        for first, second, weights in [
            ([False] * 4, [True, True, True, False], (130 / 3, 70 / 3)),
            ([False] * 4 + [True, True], [True] * 6, (3.5, 1.5)),
        ]:
            with self.subTest(answers=first):
                self.seed([{'student': {'answers': first}}, {'student': {'answers': second}}])
                self.boundary(*weights)

    def test_old_revision_progress_is_not_used_for_mastery_or_accuracy(self):
        for state, weight in [
            ({**STATES[2], 'revision': 1}, 50),
            ({**STATES[2], 'progressRevision': 1}, 30),
        ]:
            with self.subTest(state=state):
                self.seed([{'revision': 2, 'student': state}, {'student': STATES[2]}])
                self.boundary(weight)

    def test_legacy_missing_revision_defaults_to_current_revision_one(self):
        self.seed([{'student': STATES[2]}, {'student': STATES[2]}])
        self.page.evaluate("""async()=>{
          const data=await snapshotAllStores();
          for(const store of ['questions','progress','answers'])
            for(const row of data[store])delete row.revision;
          await plushInstall(data);await navigateHome('student');
        }""")
        self.boundary(3)

    def test_recent_three_are_excluded_before_weighting(self):
        # 直近の10倍問題より、残った習得済み問題を必ず選ぶ。
        self.seed([{}] * 3 + [{'student': STATES[2]}] * 2 + [{'era': 'E02'}])
        recent = [self.qid(i) for i in range(3)]
        self.assertEqual(set(self.draws([i / 100 for i in range(100)],
                                       recent=recent, previous=self.qid(0))),
                         {self.qid(3), self.qid(4)})

    def test_small_candidate_fallbacks_and_empty_era(self):
        for count, expected in [(0, {None}), (1, {self.qid(0)}),
                                (2, {self.qid(1)}), (3, {self.qid(1), self.qid(2)})]:
            with self.subTest(count=count):
                self.seed([{}] * count)
                self.assertEqual(set(self.draws([i / 100 for i in range(100)],
                                               recent=[self.qid(i) for i in range(count)],
                                               previous=self.qid(0))), expected)

    def test_all_mastered_questions_remain_eligible(self):
        self.seed([{'student': STATES[2]}] * 4)
        self.assertEqual(self.draws([0, .25, .5, .75]), [self.qid(i) for i in range(4)])

    def test_real_answers_reset_and_restore_mastery_for_following_draws(self):
        self.seed([{'student': STATES[2]}, {'student': STATES[2]}])
        self.begin()
        self.boundary(3)
        self.answer(False)
        self.assertEqual(self.page.evaluate('[currentProgress.streak,currentProgress.mastered]'), [0, False])
        self.boundary(10 * (1 + 4 * (1 - 3 / 7)))  # 5回答2正解、未習得へ戻る。
        self.next_question();self.answer();self.next_question();self.answer()
        self.assertEqual(self.page.evaluate('[currentProgress.streak,currentProgress.mastered]'), [1, False])
        self.boundary(30, 1 + 4 * (1 - 4 / 7))
        self.next_question();self.answer();self.next_question();self.answer()
        self.assertEqual(self.page.evaluate('[currentProgress.streak,currentProgress.mastered]'), [2, True])
        self.boundary(1 + 4 * (1 - 5 / 9), 2.5)
        self.assertEqual(len(self.snapshot()['answers']), 13)  # 既存8回答と今回5回答。

    def test_draws_do_not_write_history_or_change_mastery_calculations(self):
        self.seed([{}, {'student': STATES[0]}, {'student': STATES[1]},
                   {'student': STATES[2]}, {'revision': 2, 'student': {**STATES[2], 'revision': 1}}])
        before = self.snapshot()
        stats = self.page.evaluate("""async()=>{
          const records=new Map((await readAll('progress')).map(p=>[p.questionId,p]));
          const era=masteryStats('E01',records);
          return {era,overall:overallMasteryStats({E01:era}),genre:genreMasteryStats('culture',records)};
        }""")
        self.assertEqual(stats['era'], dict(count=5, mastered=1, learning=1, percentage=30, display='30'))
        self.assertEqual(stats['overall'], dict(count=5, mastered=1, learning=1, percentage=30, display='30%'))
        self.assertEqual(stats['genre']['percentage'], 30)
        self.draws([i / 100 for i in range(100)])
        self.draws([i / 100 for i in range(100)], who='test')
        self.assertEqual(self.snapshot(), before)

    def test_advance_reads_progress_for_the_selected_profile(self):
        self.seed([{'student': STATES[0], 'test': STATES[2]},
                   {'student': STATES[2], 'test': STATES[0]}])
        self.begin(.5)
        self.assertEqual(self.page.evaluate('currentQuestion.id'), self.qid(0))
        student = self.snapshot()
        self.page.evaluate('navigateHome("test")')
        self.begin(.5)
        self.assertEqual(self.page.evaluate('currentQuestion.id'), self.qid(1))
        self.answer()
        after = self.snapshot()
        for store in ['answers', 'progress', 'sessions', 'coinClaims', 'coinEvents', 'reviewEvents', 'awards']:
            self.assertEqual([r for r in after[store] if r['profile'] == 'student'],
                             [r for r in student[store] if r['profile'] == 'student'], store)
        self.assertEqual(self.draws([.5], who='student'), [self.qid(0)])

    def test_hidden_deleted_and_other_era_questions_are_not_drawn(self):
        self.seed([{}, {'deleted': True, 'student': STATES[0]}, {}, {'era': 'E02'}])
        before = self.snapshot()
        self.assertEqual(set(self.draws([i / 100 for i in range(100)])), {self.qid(0), self.qid(2)})
        self.assertTrue(self.page.evaluate('QUESTIONS.every(q=>!isSample(q.id)&&!q.deleted)'))
        self.assertEqual(self.snapshot(), before)

    def test_reload_and_page_return_keep_result_history_and_next_draw(self):
        self.seed([{'student': STATES[1]}] + [{'student': STATES[2]}] * 4)
        self.begin()
        question = self.page.evaluate('currentSession')
        self.page.reload();self.ready()
        self.assertEqual(self.page.evaluate('currentSession'), question)
        self.answer()  # streak 1 -> 2 の保存後に中断。
        before = self.snapshot()
        self.page.reload();self.ready();self.return_event()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.evaluate('[phase,currentProgress.streak,currentProgress.mastered]'),
                         ['result', 2, True])
        self.next_question(.5)
        # q0は直近除外され、同じ重みのq1〜q4の3番目が当選する。
        self.assertEqual(self.page.evaluate('currentQuestion.id'), self.qid(3))
        self.assertEqual(self.page.evaluate('currentSession.recentIds'), [self.qid(3), self.qid(0)])
        after = self.snapshot()
        for store in before:
            if store != 'sessions':
                self.assertEqual(after[store], before[store], store)
        # 再ロード後も保存済みの習得を1倍として使う（q0とq1の比較）。
        boundary = (19 / 7) / (19 / 7 + 3)
        self.assertEqual(self.draws([boundary - 1e-10, boundary + 1e-10],
                                   recent=[self.qid(i) for i in range(2, 5)]),
                         [self.qid(0), self.qid(1)])

    def test_fifty_questions_have_ten_to_one_weight_not_a_fixed_probability(self):
        self.seed([{'student': STATES[0]}] * 10 + [{'student': STATES[2]}] * 40)
        # 全問の従来重みは3。合計420を1重み刻みの中点で網羅し、乱数試行の誤差を避ける。
        draws = self.draws([(i + .5) / 420 for i in range(420)])
        learning = sum(int(q.rsplit('-', 1)[1]) < 10 for q in draws)
        self.assertEqual(learning, 300)
        self.assertEqual(len(draws) - learning, 120)
        self.assertAlmostEqual(learning / len(draws), 100 / 140)
        self.assertAlmostEqual((len(draws) - learning) / len(draws), 40 / 140)

    def test_ninety_nine_percent_prioritizes_the_remaining_learning_question(self):
        # 49問習得 + 1問連続1正解 = 49.5/50 = 99%。正答率重みは全て3。
        self.seed([{'student': STATES[1]}] + [{'student': STATES[2]}] * 49)
        self.assertEqual(self.page.evaluate("""async()=>masteryStats('E01',
          new Map((await readAll('progress')).map(p=>[p.questionId,p]))).percentage"""), 99)
        # 未習得の確率は従来1/50=2%から10/59≒16.95%へ。
        draws = self.draws([(i + .5) / 177 for i in range(177)])
        self.assertEqual(draws.count(self.qid(0)), 30)
        self.assertAlmostEqual(draws.count(self.qid(0)) / len(draws), 10 / 59)
        self.assertGreater(10 / 59, 1 / 50)
        boundary = 10 / 59
        self.assertEqual(self.draws([boundary - 1e-10, boundary + 1e-10]),
                         [self.qid(0), self.qid(1)])


if __name__ == '__main__':
    unittest.main()
