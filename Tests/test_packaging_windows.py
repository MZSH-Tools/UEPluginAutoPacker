import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'win32', 'Windows Job and directory handles')
class WindowsPackagingTests(unittest.TestCase):
    def test_descriptor_overwrite_rejects_hard_link_swap_after_check(self):
        from Source.Logic.PackagingPaths import CheckedPath
        from Source.Logic.PostProcessor import ReplaceMarketplaceURL
        from Source.Logic.WindowsHandles import RenameLeaf, WriteLeaf

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            descriptor = root / 'plugin.uplugin'
            external = root / 'external.json'
            original = b'{"MarketplaceURL":"original"}'
            descriptor.write_bytes(original)
            external.write_bytes(original)
            starting_state = descriptor.lstat()

            def swap(path):
                checked = CheckedPath(path)
                if checked == descriptor:
                    descriptor.unlink()
                    os.link(external, descriptor)
                return checked

            with patch('Source.Logic.PostProcessor.PinDirectories', side_effect=nullcontext), \
                    patch('Source.Logic.PostProcessor.CheckedPath', side_effect=swap):
                with self.assertRaises(ValueError):
                    ReplaceMarketplaceURL(descriptor)
            with self.assertRaises(ValueError):
                WriteLeaf(descriptor, b'not written', descriptor.lstat())
            self.assertEqual(external.read_bytes(), original)

            descriptor.unlink()
            os.replace(external, descriptor)
            with self.assertRaises(ValueError):
                WriteLeaf(descriptor, b'not written', starting_state)
            with self.assertRaises(ValueError):
                RenameLeaf(descriptor, 'unusable', starting_state)
            self.assertEqual(descriptor.read_bytes(), original)
            self.assertFalse((root / 'unusable').exists())

    def test_pinned_ancestor_cannot_be_replaced_with_junction(self):
        from Source.Logic.PackagingPaths import PinDirectories, RenameSibling

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent = root / 'parent'
            parent.mkdir()
            external = root / 'external'
            external.mkdir()
            link = root / 'link'
            subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(external)],
                           check=True, capture_output=True)
            with PinDirectories(parent):
                with self.assertRaises(PermissionError):
                    parent.rename(root / 'moved')
                with self.assertRaises(ValueError):
                    with PinDirectories(link):
                        self.fail('junction accepted')
                (parent / 'ordinary').mkdir()
                RenameSibling(parent / 'ordinary', parent / 'published')
            parent.rename(root / 'moved')
            link.rename(parent)
            self.assertFalse((external / 'published').exists())

    def test_child_environment_ignores_dangerous_overrides(self):
        from Source.Logic.BuildRunner import BuildEnvironment

        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary).resolve()
            names = ('uebp_LOCAL_ROOT', 'uebp_EngineSavedFolder', 'uebp_LogFolder',
                     'uebp_FinalLogFolder', 'uebp_CSVFile', 'TMP', 'TEMP')
            inherited = {name.swapcase(): 'wrong' for name in names}
            inherited['INCLUDE'] = 'compiler'
            environment = BuildEnvironment(stage, inherited)
            self.assertEqual(environment['INCLUDE'], 'compiler')
            self.assertNotIn(names[0].casefold(), {name.casefold() for name in environment})
            for name in names[1:]:
                self.assertIn(stage, Path(environment[name]).parents)

    def test_job_waits_for_owned_descendant_and_confirms_empty(self):
        from Source.Logic.WindowsJob import WindowsJob

        with tempfile.TemporaryDirectory() as temporary, WindowsJob() as job:
            marker = Path(temporary) / 'done'
            child = f'import time; from pathlib import Path; time.sleep(.25); Path({str(marker)!r}).touch()'
            parent = f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}])'
            process = job.Launch([sys.executable, '-c', parent])
            self.assertEqual(job.Wait(process), 0)
            self.assertTrue(marker.exists())
