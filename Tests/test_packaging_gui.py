import ctypes
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide2 import QtWidgets

import Main
from Source.Logic.BuildWorker import BuildWorker
from Source.Logic.Packaging import BuildOptions
from Source.UI.MainWindow import MainWindow


class PackagingGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_single_build_flow_compression_controls_and_build_button(self):
        window = MainWindow()
        self.addCleanup(window.close)
        events = []
        window.BuildRequested.connect(lambda: events.append('build'))
        self.assertEqual(window.findChildren(QtWidgets.QComboBox), [window.PluginBox])
        self.assertFalse(window.AutoZip.isChecked())
        self.assertFalse(window.DeleteOutput.isEnabled())
        self.assertFalse(window.GetBuildOptions().DeleteOutput)
        self.assertTrue(window.GetBuildOptions().AddVersion)
        options = window.GetBuildOptions()
        self.assertEqual(options.Profile, 'deploy')
        self.assertFalse(options.MakeZip)
        window.AutoZip.click()
        self.assertTrue(window.DeleteOutput.isEnabled())
        window.DeleteOutput.click()
        options = window.GetBuildOptions()
        self.assertEqual(options.Profile, 'deploy')
        self.assertTrue(options.MakeZip)
        self.assertTrue(options.DeleteOutput)
        window.AutoZip.click()
        self.assertFalse(window.GetBuildOptions().MakeZip)
        self.assertFalse(window.DeleteOutput.isChecked())
        self.assertFalse(window.DeleteOutput.isEnabled())
        self.assertFalse(window.GetBuildOptions().DeleteOutput)
        window.FabOptions['自动添加版本信息'].click()
        self.assertFalse(window.GetBuildOptions().AddVersion)
        window.BtnBuild.click()
        self.assertEqual(events, ['build'])
        self.assertEqual(window.layout().itemAtPosition(1, 1).widget(), window.BtnBuild)

    def test_worker_never_marks_post_failure_successful(self):
        engine = {'Name': '5.4', 'Path': 'dummy'}
        worker = BuildWorker([engine], 'Example', 'Example.uplugin', 'output',
                             AllEngines=[engine], Options=BuildOptions('fab'))
        statuses, logs, finished = [], [], []
        worker.StatusSignal.connect(lambda index, status: statuses.append(status))
        worker.LogSignal.connect(lambda record, level: logs.append((record, level)))
        worker.FinishedSignal.connect(lambda: finished.append(True))
        with patch('Source.Logic.BuildWorker.RunPackaging', side_effect=ValueError('post error')):
            worker.run()
        self.assertEqual(statuses, ['打包中', '❌ 失败'])
        self.assertTrue(any('post error' in record[1] and level == 'error' for record, level in logs))
        self.assertEqual(finished, [True])

    def test_worker_stop_during_commit_finishes_current_and_cancels_next(self):
        engines = [{'Name': 'first'}, {'Name': 'next'}]
        worker = BuildWorker(engines, 'Example', 'Example.uplugin', 'output')
        statuses, logs = [], []
        worker.StatusSignal.connect(lambda index, status: statuses.append((index, status)))
        worker.LogSignal.connect(lambda record, level: logs.append(record))

        def stop_during_commit(*args, Gate, **kwargs):
            with Gate.Commit():
                worker.Stop()
            return ('output',)

        with patch('Source.Logic.BuildWorker.RunPackaging', side_effect=stop_during_commit) as run:
            worker.run()
        run.assert_called_once()
        self.assertEqual(statuses, [(0, '打包中'), (0, '✅ 成功'), (1, '已取消')])
        self.assertTrue(any(name == 'first' and '已进入提交' in line for name, line in logs))

    def test_only_packaged_gui_hides_console(self):
        with patch.object(Main.sys, 'platform', 'win32'), patch.object(ctypes, 'windll', create=True) as api:
            api.kernel32.GetConsoleWindow.return_value = 123
            for frozen, argv in ((False, ['Main.py']), (True, ['Example.exe', 'engines']),
                                 (True, ['Example.exe'])):
                api.reset_mock()
                with patch.object(sys, 'frozen', frozen, create=True), patch.object(sys, 'argv', argv):
                    Main.HideConsoleForPackagedGui()
                if frozen and len(argv) == 1:
                    api.kernel32.GetConsoleWindow.assert_called_once_with()
                    api.user32.ShowWindow.assert_called_once_with(123, 0)
                else:
                    api.kernel32.GetConsoleWindow.assert_not_called()
                    api.user32.ShowWindow.assert_not_called()
