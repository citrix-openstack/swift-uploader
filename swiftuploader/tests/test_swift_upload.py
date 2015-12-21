import datetime
import mock
import time
import stat
import unittest
import os

from swiftuploader import upload

class TestUtilities(unittest.TestCase):
    def test_start_stansa(self):
        prefix = 'test_prefix'
        self.assertIn(prefix, upload._html_start_stansa(prefix))

    def test_file_stansa(self):
        filename = 'test_filename'
        size = 'test_size'
        modified = 'test_modified'
        html = upload._html_file_stansa(filename, modified, size)
        self.assertIn(filename, html)
        self.assertIn(size, html)
        self.assertIn(modified, html)

    def test_content_encoding_none(self):
        self.assertEqual(None, upload.get_content_encoding('filename.txt'))
        self.assertEqual(None, upload.get_content_encoding('filename'))
        self.assertEqual(None, upload.get_content_encoding('filename.log'))

    def test_content_encoding_gz(self):
        self.assertEqual('gzip', upload.get_content_encoding('filename.txt.gz'))
        self.assertEqual('gzip', upload.get_content_encoding('filename.gz'))
        self.assertEqual('gzip', upload.get_content_encoding('filename.log.gz'))
        self.assertEqual('gzip', upload.get_content_encoding('var/log/messages.1.gz'))

    def test_content_type_gz(self):
        self.assertEqual('text/plain', upload.get_content_type('filename.txt.gz'))
        self.assertEqual('text/plain', upload.get_content_type('filename.log.gz'))
        self.assertEqual('text/plain', upload.get_content_type('filename.conf.gz'))
        self.assertEqual('text/plain', upload.get_content_type('filename.sh.gz'))
        self.assertEqual('text/html', upload.get_content_type('filename.html.gz'))
        self.assertEqual(None, upload.get_content_type('filename.dat.gz'))
        self.assertEqual('text/plain', upload.get_content_type('messages.1.gz'))
        self.assertEqual('text/plain', upload.get_content_type('SMlog.1.gz'))
        self.assertEqual('text/plain', upload.get_content_type('var/log/messages.1.gz'))
        self.assertEqual('text/plain', upload.get_content_type('var/log/SMlog.1.gz'))

    def test_content_type(self):
        self.assertEqual('text/plain', upload.get_content_type('filename.txt'))
        self.assertEqual('text/plain', upload.get_content_type('filename.log'))
        self.assertEqual('text/plain', upload.get_content_type('filename.conf'))
        self.assertEqual('text/plain', upload.get_content_type('filename.sh'))
        self.assertEqual('text/html', upload.get_content_type('filename.html'))
        self.assertEqual(None, upload.get_content_type('filename.dat'))
        self.assertEqual('text/plain', upload.get_content_type('messages'))
        self.assertEqual('text/plain', upload.get_content_type('SMlog'))
        self.assertEqual('text/plain', upload.get_content_type('var/log/messages'))
        self.assertEqual('text/plain', upload.get_content_type('var/log/SMlog'))

class TestSwiftUploader(unittest.TestCase):
    def setUp(self):
        self.mock_stat_file = mock.Mock()
        self.mock_stat_file.st_mode = stat.S_IFREG
        self.mock_stat_file.st_size = 1024
        self.mock_stat_file.st_mtime = 1.0
        self.mock_stat_dir = mock.Mock()
        self.mock_stat_dir.st_mode = stat.S_IFDIR

