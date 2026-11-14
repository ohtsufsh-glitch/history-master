"""Issue #48: 通貨UIの名称・単位・狭幅表示を公開可能な合成データで確認。"""
from html.parser import HTMLParser
import unittest

import quiz_coin_display_test as coins
from plush_test import ROOT


class CoinWordingTest(unittest.TestCase):
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

    def test_static_copy_and_accessibility_labels_use_coin_and_mai(self):
        class UiText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.skip = False
                self.values = []

            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style'):
                    self.skip = True
                self.values.extend(value for name, value in attrs if value and
                                   name in ('aria-label', 'alt', 'title', 'placeholder'))

            def handle_endtag(self, tag):
                if tag in ('script', 'style'):
                    self.skip = False

            def handle_data(self, data):
                if not self.skip:
                    self.values.append(data)

        parser = UiText()
        parser.feed((ROOT / 'index.html').read_text())
        ui = ' '.join(parser.values)
        self.assertNotIn('金貨', ui)
        self.assertNotRegex(ui, r'[0-9][0-9,]*\s*コイン')
        self.assertIn('コイン100枚でプレイ', ui)
        self.assertEqual(self.page.locator('#quiz-coins').get_attribute('aria-label'), 'コイン残高')

    def test_price_confirmation_and_shortage_keep_saved_amounts(self):
        self.page.evaluate("""async()=>{
          await plushInstall(plushFixture());await navigateHome('student');
        }""")
        self.assertEqual(' '.join(self.page.locator('#home-coins').inner_text().split()), 'コイン 805枚')
        self.assertEqual(self.page.locator('#arcade-home-cost-text').inner_text(), 'コイン100枚 / 1プレイ')
        self.assertIn('コインを使って', self.page.locator('#arcade-home-description').inner_text())
        self.page.evaluate('openArcade()')
        self.assertEqual(self.page.locator('#arcade-balance').inner_text(), '805枚')
        self.assertEqual(self.page.locator('#crane-start').inner_text(), 'コイン100枚でプレイ')
        self.assertEqual(self.page.locator('#arcade-message').inner_text(), 'コイン100枚で1回遊べます。')
        before = self.snapshot()
        dialogs = []
        self.page.on('dialog', lambda dialog: dialogs.append(dialog.message))
        self.page.evaluate('startCrane()')
        self.assertEqual(dialogs, ['コイン100枚を使ってUFOキャッチャーを1回遊びますか？\n現在のコイン：805枚'])
        self.assertEqual(self.page.evaluate('getAvailableCoins()'), 705)
        self.assertEqual(self.page.locator('#arcade-balance').inner_text(), '705枚')
        after = self.snapshot()
        self.assertEqual([r['amount'] for r in after['coinSpends']], [100])
        for name in ('coinEvents', 'reviewEvents', 'coinClaims'):
            self.assertEqual(after[name], before[name])
        for name in before:
            self.assertEqual([r for r in after[name] if r.get('profile') == 'test'],
                             [r for r in before[name] if r.get('profile') == 'test'], name)
        # 支払前の合成データから65枚の状態を作り、不足数だけを表示する。
        before['reviewEvents'] = ([r for r in before['reviewEvents'] if r['profile'] == 'student'][:30] +
                                  [r for r in before['reviewEvents'] if r['profile'] == 'test'])
        self.page.evaluate('async data=>{await plushInstall(data);await openArcade();}', before)
        saved = self.snapshot()
        self.assertEqual(self.page.locator('#arcade-balance').inner_text(), '65枚')
        self.assertEqual(self.page.locator('#crane-start').inner_text(), 'あと35枚必要')
        self.assertTrue(self.page.locator('#crane-start').is_disabled())
        self.page.evaluate('startCrane()')
        self.assertEqual(self.snapshot(), saved)
        error = self.page.evaluate('''async()=>{
          try{await purchaseCranePlay(newArcadePlay('student'));return null;}
          catch(error){return error.message;}
        }''')
        self.assertEqual(error, '景品がないか、コイン不足、または進行中のプレイがあります')
        self.assertEqual(self.snapshot(), saved)

    def test_iphone_ipad_currency_layout_preserves_question_gold_wording(self):
        question = '合成史料の「金貨」という語を確認する架空問題です。'
        explanation = '説明中の「金貨」も学習内容としてそのまま表示します。'
        self.page.evaluate("""async ({question,explanation})=>{
          const data=await snapshotAllStores();
          const q=data.questions.find(q=>q.era==='E01');q.q=question;q.why=explanation;
          await plushInstall(data);await ensureArcadeBoards();await navigateHome('student');
        }""", {'question': question, 'explanation': explanation})
        self.quiz()
        self.answer()
        self.assertEqual(self.page.locator('#question-text').inner_text(), question)
        self.assertIn(explanation, self.page.locator('#result').inner_text())
        self.assertIn('コインを2枚獲得！', self.page.locator('#result').inner_text())
        before = self.snapshot()
        for width, height in [(320, 568), (375, 812), (390, 844), (768, 1024), (1024, 768)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                for screen, selectors in [
                    ('quiz', ['.coin-reward', '.coin-reward-title', '#quiz-coins']),
                    ('home', ['#home-coins', '#arcade-home-cost-text', '#arcade-home-description']),
                    ('arcade', ['#crane-start', '#arcade-balance', '#arcade-message']),
                ]:
                    if screen == 'quiz':
                        self.quiz()
                    elif screen == 'home':
                        self.page.evaluate('navigateHome()')
                    else:
                        self.page.evaluate('openArcade()')
                    self.assertTrue(self.page.evaluate("""selectors=>
                      document.documentElement.scrollWidth<=innerWidth&&selectors.every(selector=>{
                        const el=document.querySelector(selector),r=el.getBoundingClientRect();
                        const range=document.createRange();range.selectNodeContents(el);
                        const text=range.getBoundingClientRect();
                        return r.width>0&&r.left>=0&&r.right<=innerWidth&&
                          el.scrollWidth<=el.clientWidth+1&&text.left>=r.left-1&&text.right<=r.right+1;
                      })""", selectors), (width, screen))
        self.assertEqual(self.snapshot(), before)
