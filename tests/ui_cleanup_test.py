"""v1.6.6のUI回帰テスト。実行方法はquestion_editor_test.pyと同じ。

localhostと一時ブラウザ、既存テストの公開可能な合成データだけを使用する。
"""

import functools
import http.server
import os
import re
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright

from plush_test import FIXTURE_HELPERS, ROOT, QuietHandler


TEST_NOTE = '🔧 テストモード：金貨を消費せず何回でも遊べます。景品と履歴はテスト用に保存されます。'


class UiCleanupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        executable = os.environ.get('HISTORY_MASTER_BROWSER') or shutil.which('chromium')
        cls.browser = cls.playwright.chromium.launch(executable_path=executable)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/index.html'

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('console', lambda message: self.errors.append(message.text) if message.type == 'error' else None)
        self.page.on('dialog', lambda dialog: dialog.accept())
        self.page.route('**/favicon.ico', lambda route: route.fulfill(status=204))
        self.page.goto(self.url)
        self.ready()

    def ready(self):
        self.page.wait_for_function("(typeof appReady==='undefined'?document.querySelectorAll('#era-list button').length===10:appReady)")

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def assert_header(self, mode):
        self.assertEqual(self.page.locator('#header-coins, #header-coin-amount').count(), 0)
        label = self.page.locator('#header-mode')
        self.assertEqual(label.count(), 1)
        # 430px以下ではラベルを隠す既存のレスポンシブ仕様を維持する。
        self.assertEqual(label.is_visible(), self.page.viewport_size['width'] > 430)
        self.assertEqual(label.text_content(), mode)
        self.assertEqual(self.page.locator('#open-admin').count(), 1)

    def assert_student_note_removed(self):
        note = self.page.locator('#arcade-profile-note')
        self.assertFalse(note.is_visible())
        self.assertEqual(note.text_content(), '')
        self.assertEqual(note.evaluate('el=>el.getBoundingClientRect().height'), 0)

    def test_version_is_admin_only_and_follows_the_constant(self):
        before = self.page.evaluate('snapshotAllStores()')
        self.assertFalse(self.page.locator('#app-version').is_visible())
        self.assertNotIn('アプリバージョン', self.page.locator('#home').inner_text())
        self.assertEqual(self.page.locator('#home #app-version').count(), 0)
        self.page.locator('#open-admin').click()
        version = self.page.locator('#app-version')
        self.assertTrue(version.is_visible())
        self.assertEqual(version.inner_text(), 'アプリバージョン：v1.6.13')
        self.assertEqual(version.inner_text(), 'アプリバージョン：' + self.page.evaluate('APP_VERSION'))
        self.assertEqual(version.evaluate('el=>el.previousElementSibling.textContent'), '⚙️ 保護者用管理画面')
        self.assertEqual(self.page.evaluate('[DB_NAME,DB_VERSION,BACKUP_VERSION]'),
                         ['history-master-sample-v1', 8, 8])
        self.assertEqual(self.page.evaluate('snapshotAllStores()'), before)
        # 定数だけを変えた将来のリリースでも、表示に追従することを確認。
        source, count = re.subn(r'(const APP_VERSION\s*=\s*)["\'][^"\']+["\']',
                                lambda match: match[1] + '"v9.9.9"',
                                (ROOT / 'index.html').read_text(), count=1)
        self.assertEqual(count, 1)
        self.page.route(self.url, lambda route: route.fulfill(body=source, content_type='text/html'))
        self.page.reload()
        self.ready()
        # 履歴にある管理画面をリロード後も復元する。
        self.assertTrue(self.page.locator('#admin').is_visible())
        self.assertEqual(self.page.locator('#app-version').inner_text(), 'アプリバージョン：v9.9.9')
        self.assertEqual(self.page.evaluate('snapshotAllStores()'), before)

    def test_coin_displays_and_notes_follow_profile_and_screen_changes(self):
        self.page.evaluate(FIXTURE_HELPERS)
        self.page.evaluate('async()=>{await plushInstall(plushFixture());await renderHome();}')
        self.assert_header('👧 学習用')
        self.assertTrue(self.page.locator('#open-admin').is_visible())
        self.assertTrue(self.page.locator('#home-coins').is_visible())
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '805')
        self.page.locator('#open-arcade').click()
        self.page.wait_for_function("document.querySelector('#arcade-balance').textContent==='805'")
        self.assert_header('👧 学習用')
        self.assert_student_note_removed()
        self.assertEqual(self.page.locator('#arcade-hint').inner_text(), '途中で閉じても続きから再開できます。')
        self.page.locator('#crane-start').click()
        self.page.wait_for_function("arcadePlay?.status==='aiming'&&!arcadeBusy")
        self.assertEqual(self.page.locator('#arcade-balance').inner_text(), '705')
        self.assertEqual(self.page.locator('#home-coin-amount').text_content(), '705')
        self.page.locator('#arcade-back').click()
        self.page.wait_for_function("!document.querySelector('#home').classList.contains('hidden')")
        student = self.page.evaluate('snapshotAllStores()')
        self.page.locator('#open-admin').click()
        self.assert_header('🔧 保護者用')
        self.page.locator('#admin-start-test').click()
        self.page.wait_for_function("profile==='test'&&!document.querySelector('#home').classList.contains('hidden')")
        self.assert_header('🔧 テスト中')
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '9')
        self.page.locator('#open-arcade').click()
        self.page.wait_for_function("document.querySelector('#arcade-balance').textContent==='∞（無料）'")
        self.assertTrue(self.page.locator('#arcade-profile-note').is_visible())
        self.assertEqual(self.page.locator('#arcade-profile-note').inner_text(), TEST_NOTE)
        self.page.locator('#crane-start').click()
        self.page.wait_for_function("arcadePlay?.profile==='test'&&arcadePlay.status==='aiming'&&!arcadeBusy")
        self.assertEqual(self.page.evaluate("getAvailableCoins('test')"), 9)
        self.page.locator('#open-admin').click()
        self.assert_header('🔧 保護者用')
        self.page.locator('#admin-back').click()
        self.page.wait_for_function("profile==='student'&&!document.querySelector('#home').classList.contains('hidden')")
        self.assert_header('👧 学習用')
        self.assertEqual(self.page.locator('#home-coin-amount').inner_text(), '705')
        self.page.locator('#open-arcade').click()
        self.page.wait_for_function("document.querySelector('#arcade-balance').textContent==='705'")
        self.assert_student_note_removed()
        self.assertIsNone(self.page.evaluate('arcadeSweepFrame'))
        after = self.page.evaluate('snapshotAllStores()')
        for store in student:
            self.assertEqual([r for r in after[store] if r.get('profile') == 'student'],
                             [r for r in student[store] if r.get('profile') == 'student'], store)

    def test_layout_at_iphone_and_ipad_sizes(self):
        for width, height in [(375, 812), (390, 844), (1024, 768), (1180, 820)]:
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.page.evaluate('returnToStudentHome()')
                self.assert_header('👧 学習用')
                self.page.locator('#open-admin').click()
                version = self.page.locator('#app-version')
                self.assertTrue(version.is_visible())
                self.assertTrue(version.evaluate("""el=>{
                  const r=el.getBoundingClientRect(), size=parseFloat(getComputedStyle(el).fontSize);
                  return r.left>=0&&r.right<=innerWidth&&size>=12&&size<=16;
                }"""))
                self.page.locator('#admin-start-test').click()
                self.page.wait_for_function("profile==='test'&&!document.querySelector('#home').classList.contains('hidden')")
                self.page.locator('#open-arcade').click()
                self.page.wait_for_function("!document.querySelector('#arcade-profile-note').classList.contains('hidden')")
                self.assertEqual(self.page.locator('#arcade-profile-note').inner_text(), TEST_NOTE)
                self.assertTrue(self.page.evaluate("""()=>{
                  const selectors=['#open-admin','#arcade-profile-note','#arcade-balance','#arcade-hint'];
                  if(innerWidth>430)selectors.push('#header-mode');
                  return document.documentElement.scrollWidth<=innerWidth&&selectors.every(selector=>{
                    const r=document.querySelector(selector)?.getBoundingClientRect();
                    return r&&r.width>0&&r.left>=0&&r.right<=innerWidth;
                  });
                }"""))


if __name__ == '__main__':
    unittest.main()
