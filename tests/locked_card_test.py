"""Issue #43: 未獲得カードの裏面・画像要求・拡大・保護者プレビュー。

準備・実行環境は question_editor_test.py と同じ。関連テストだけを実行:
python -m unittest discover -s tests -p 'locked_card_test.py' -v
localhost・一時Chromium・架空の獲得情報のみ使用。Safari実機は別途確認する。
"""

import re
import unittest

import question_editor_test as editor


BACK = 'assets/cards/card-back.webp'
FRONT = re.compile(r'/assets/cards/E\d{2}\.webp(?:\?|$)')


class LockedCardTest(unittest.TestCase):
    setUpClass = classmethod(editor.QuestionEditorTest.setUpClass.__func__)
    tearDownClass = classmethod(editor.QuestionEditorTest.tearDownClass.__func__)
    tearDown = editor.QuestionEditorTest.tearDown

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.errors = []
        self.requests = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.requests.append(request.url))
        self.page.on('dialog', lambda dialog: dialog.accept())
        self.page.goto(self.url)
        self.page.wait_for_function('appReady')

    def snapshot(self):
        return self.page.evaluate('snapshotAllStores()')

    def load_image(self, image):
        # lazy画像を実際に画面内へ移し、src属性だけでなく実ファイルも確認する。
        image.locator('..').scroll_into_view_if_needed()
        image.evaluate("img=>new Promise((resolve,reject)=>{\n"
                       "if(img.complete) return img.naturalWidth ? resolve() : reject('画像読込失敗');\n"
                       "img.addEventListener('load',resolve,{once:true});\n"
                       "img.addEventListener('error',()=>reject('画像読込失敗'),{once:true});})")
        self.assertEqual(image.evaluate('img=>[img.naturalWidth,img.naturalHeight]'), [720, 960])

    def assert_layout(self, gallery):
        self.assertTrue(self.page.evaluate(
            'document.documentElement.scrollWidth<=innerWidth'), '画面全体に横はみ出し')
        self.assertTrue(gallery.evaluate("""gallery=>[...gallery.children].every(card=>{
          const g=gallery.getBoundingClientRect(),r=card.getBoundingClientRect();
          const art=card.querySelector('.card-art').getBoundingClientRect();
          return r.left>=g.left-1&&r.right<=g.right+1&&art.width>0&&
            Math.abs(art.width/art.height-.75)<.01&&card.scrollWidth<=card.clientWidth+1;
        })"""), 'カードのはみ出し、または3:4比率の崩れ')

    def test_shared_back_image_loads(self):
        self.load_image(self.page.locator('#card-gallery .locked img').first)

    def test_all_locked_cards_request_only_shared_back_and_do_not_open(self):
        before = self.snapshot()
        gallery = self.page.locator('#card-gallery')
        self.assertEqual(gallery.locator('.trophy.locked').count(), 10)
        self.assertEqual(gallery.locator('button').count(), 0)
        self.assertEqual(self.page.locator('img[src^="assets/cards/E"]').count(), 0)
        for card in gallery.locator('.trophy').all():
            self.assertEqual(card.locator('img').get_attribute('src'), BACK)
            self.assertEqual(card.locator('.trophy-name').inner_text(), 'まだ秘密のカード')
            self.assertTrue(card.locator('.trophy-era').inner_text())
            self.assertRegex(card.locator('.trophy-status').inner_text(), r'^(登録|習得)あと\d+問$')
            card.scroll_into_view_if_needed()
            self.assertEqual(card.locator('img').evaluate('img=>getComputedStyle(img).filter'), 'none')
            card.tap()
            self.assertFalse(self.page.locator('#card-detail-dialog').evaluate('dialog=>dialog.open'))
        self.assertTrue(any(url.endswith('/' + BACK) for url in self.requests))
        self.assertEqual([url for url in self.requests if FRONT.search(url)], [])
        self.assertEqual(self.snapshot(), before)
        for width in [390, 768]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': 1024})
                self.assert_layout(gallery)

    def test_owned_front_zoom_close_and_profile_specific_backs(self):
        self.page.evaluate("""async()=>{
          await writeAwards([
            {key:'student:E01',profile:'student',era:'E01',earnedAt:'2020-01-01T00:00:00Z',questionCountAtEarn:50},
            {key:'test:E02',profile:'test',era:'E02',earnedAt:'2020-01-01T00:00:00Z',questionCountAtEarn:50}
          ]);
          await renderHome();
        }""")
        before = self.snapshot()
        for who, era in [('student', 'E01'), ('test', 'E02')]:
            with self.subTest(profile=who):
                self.page.evaluate('who=>navigateHome(who)', who)
                gallery = self.page.locator('#card-gallery')
                earned = gallery.locator('button.trophy-open')
                self.assertEqual(earned.count(), 1)
                self.assertEqual(earned.locator('img').get_attribute('src'), f'assets/cards/{era}.webp')
                self.load_image(earned.locator('img'))
                self.assertEqual(gallery.locator('.locked img').evaluate_all(
                    'imgs=>imgs.map(img=>img.getAttribute("src"))'), [BACK] * 9)
                for width in [390, 768]:
                    self.page.set_viewport_size({'width': width, 'height': 1024})
                    self.assert_layout(gallery)
                    for close in ['button', 'backdrop']:
                        earned.tap()
                        dialog = self.page.locator('#card-detail-dialog')
                        self.assertTrue(dialog.evaluate('dialog=>dialog.open'))
                        image = dialog.locator('img')
                        self.assertEqual(image.get_attribute('src'), f'assets/cards/{era}.webp')
                        self.load_image(image)
                        bounds = dialog.bounding_box()
                        self.assertGreaterEqual(bounds['x'], 0)
                        self.assertLessEqual(bounds['x'] + bounds['width'], width + 1)
                        if close == 'button':
                            dialog.get_by_role('button', name='✕ 閉じる', exact=True).tap()
                        else:
                            self.page.touchscreen.tap(2, 2)
                        self.assertFalse(dialog.evaluate('dialog=>dialog.open'))
        self.assertEqual(self.snapshot(), before)

    def test_admin_previews_all_ten_fronts_without_awarding(self):
        before = self.snapshot()
        self.page.locator('#open-admin').tap()
        self.page.locator('#admin-other-group > summary').tap()
        self.page.locator('#card-preview-panel > summary').tap()
        self.page.wait_for_function('document.querySelectorAll("#admin-card-preview button").length===10')
        gallery = self.page.locator('#admin-card-preview')
        for index, card in enumerate(gallery.locator('button').all(), 1):
            expected = f'assets/cards/E{index:02d}.webp'
            self.assertEqual(card.locator('img').get_attribute('src'), expected)
            self.load_image(card.locator('img'))
            card.tap()
            dialog = self.page.locator('#card-detail-dialog')
            self.assertTrue(dialog.evaluate('dialog=>dialog.open'))
            self.assertEqual(dialog.locator('img').get_attribute('src'), expected)
            self.assertIn('獲得状況は変更されません', dialog.inner_text())
            dialog.get_by_role('button', name='✕ 閉じる', exact=True).tap()
        for width in [390, 768]:
            self.page.set_viewport_size({'width': width, 'height': 1024})
            self.assert_layout(gallery)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.page.locator('#card-gallery .locked').count(), 10)
