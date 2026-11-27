import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from contextlib import redirect_stderr
from unittest.mock import Mock, patch

from Source.Logic.CliRunner import ParseArgs
from Source.Logic.Packaging import BuildOptions, RunPackaging, TargetLock


class PackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        settings = patch('Source.Logic.PostProcessor.ConfigManager', return_value=Mock(Get=Mock(return_value={})))
        self.addCleanup(settings.stop)
        settings.start()
        version_settings = patch('Source.Logic.Packaging.ConfigManager', return_value=Mock(Get=Mock(return_value={})))
        self.addCleanup(version_settings.stop)
        version_settings.start()
        self.source = self.root / 'project/Plugins/Example/Example.uplugin'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(json.dumps({'FileVersion': 3, 'Modules': [{'Name': 'Example'}],
                                            'Installed': False, 'EnabledByDefault': True,
                                            'EngineVersion': '5.2.0'}).encode())
        engine_root = self.root / 'engine'
        build = engine_root / 'Engine/Build'
        (build / 'BatchFiles').mkdir(parents=True)
        (build / 'BatchFiles/RunUAT.bat').touch()
        (build / 'Build.version').write_text(json.dumps({'MajorVersion': 5, 'MinorVersion': 4, 'PatchVersion': 3}))
        engine_manifest = engine_root / 'Engine/Binaries/Win64/UnrealEditor.modules'
        engine_manifest.parent.mkdir(parents=True)
        engine_manifest.write_text(json.dumps({'BuildId': 'example', 'Modules': {}}))
        self.engine = {'Name': '5.4', 'Path': str(engine_root)}
        self.output = self.root / 'output'
        self.final = self.output / 'Example/5.4'
        self.archive = self.final.with_name('Example_UE_5.4_Source.zip')

    def payload(self, destination, version=None):
        destination.mkdir(parents=True, exist_ok=True)
        descriptor = {'FileVersion': 3, 'Modules': [{'Name': 'Example', 'PlatformAllowList': ['Win64']}],
                      'Installed': True, 'MarketplaceURL':
                      'com.epicgames.launcher://ue/marketplace/product/12345678-1234-1234-1234-123456789abc'}
        if version is not None:
            descriptor['EngineVersion'] = version
        (destination / 'Example.uplugin').write_text(json.dumps(descriptor))
        for member in ('Source/Example/Example.Build.cs', 'Source/Tests/Test.cpp', 'Tests/Test.cpp',
                       'Shaders/code.usf', 'Binaries/Win64/UnrealEditor-Example.dll',
                       'Binaries/Win64/UnrealEditor-Example.pdb', 'Binaries/ThirdParty/Vendor/vendor.dll',
                       'Intermediate/Build/obj.obj', '.git/config', '.codex/config.toml'):
            target = destination / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'payload')
        (destination / 'Binaries/Win64/UnrealEditor.modules').write_text(
            json.dumps({'BuildId': 'example', 'Modules': {'Example': 'UnrealEditor-Example.dll'}}))

    def runner(self, Runner):
        def generate():
            staged_source = Path(Runner.call_args.kwargs['PluginPath'])
            self.assertNotEqual(staged_source, self.source)
            self.assertNotIn('EngineVersion', json.loads(staged_source.read_text(encoding='utf-8')))
            staged_source.write_text('modified only by fake UAT')
            self.payload(Path(Runner.call_args.kwargs['OutputDir']))
            yield 'EXIT_SUCCESS'
        Runner.return_value.RunBuild.side_effect = generate

    def run_job(self, options=None, zip_only=False):
        return RunPackaging(self.engine, [self.engine], 'Example', self.source, self.output,
                            options or BuildOptions(), ZipOnly=zip_only, Log=lambda line: None)

    def test_build_version_and_flags_are_written_only_to_copy(self):
        original = self.source.read_bytes()
        with patch('Source.Logic.Packaging.BuildRunner') as Runner:
            self.runner(Runner)
            self.run_job(BuildOptions('deploy'))
        descriptor = json.loads((self.final / 'Example.uplugin').read_text())
        self.assertEqual(descriptor['EngineVersion'], '5.4.3')
        self.assertIs(descriptor['Installed'], False)
        self.assertIs(descriptor['EnabledByDefault'], True)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertTrue((self.final / 'Binaries/Win64/UnrealEditor-Example.dll').exists())

    def test_optional_version_metadata_matches_directory_and_zip(self):
        original = self.source.read_bytes()
        with patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            self.run_job(BuildOptions('deploy', Zip=True, AddVersion=False))
        self.assertNotIn('EngineVersion', json.loads((self.final / 'Example.uplugin').read_text()))
        with zipfile.ZipFile(self.archive) as archive:
            self.assertNotIn('EngineVersion', json.loads(archive.read('Example/Example.uplugin')))
        self.assertEqual(self.source.read_bytes(), original)

    def test_version_default_uses_saved_setting_and_explicit_override(self):
        settings = Mock(Get=Mock(return_value={'自动添加版本信息': False}))
        with patch('Source.Logic.Packaging.ConfigManager', return_value=settings), patch(
                'Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            self.run_job(BuildOptions('deploy'))
            self.assertNotIn('EngineVersion', json.loads((self.final / 'Example.uplugin').read_text()))
            self.run_job(BuildOptions('deploy', AddVersion=True))
        self.assertEqual(json.loads((self.final / 'Example.uplugin').read_text())['EngineVersion'], '5.4.3')

    def test_cli_controls_compression_cleanup_and_version(self):
        self.assertEqual(ParseArgs(['build', 'Example']).Options.Profile, 'deploy')
        options = ParseArgs(['build', 'Example', '--zip', '--delete-output-after-zip',
                             '--no-add-version']).Options
        self.assertTrue(options.MakeZip)
        self.assertTrue(options.DeleteOutput)
        self.assertFalse(options.AddVersion)
        options = ParseArgs(['build', 'Example', '--no-zip', '--keep-output', '--add-version']).Options
        self.assertFalse(options.MakeZip)
        self.assertFalse(options.DeleteOutput)
        self.assertTrue(options.AddVersion)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            ParseArgs(['build', 'Example', '--no-zip', '--delete-output-after-zip'])
        self.assertEqual(error.exception.code, 2)

    def test_compression_cleanup_removes_only_matching_engine_output(self):
        original_source = self.source.read_bytes()
        self.payload(self.final, version='5.4.3')
        other = self.final.with_name('UE_5.7')
        self.payload(other)
        other_zip = self.archive.with_name('Example_UE_5.7_Source.zip')
        other_zip.write_bytes(b'other engine archive')
        other_files = {file.relative_to(other): file.read_bytes() for file in other.rglob('*') if file.is_file()}
        for existing_output in (True, False):
            with self.subTest(existing_output=existing_output), patch('Source.Logic.Packaging.BuildRunner') as runner:
                self.runner(runner)
                artifacts = self.run_job(BuildOptions('deploy', Zip=True, DeleteOutput=True, AddVersion=True))
            self.assertEqual(artifacts, (self.archive,))
            self.assertFalse(self.final.exists())
            with zipfile.ZipFile(self.archive) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn('Example/Source/Example/Example.Build.cs', archive.namelist())
            self.assertEqual(self.source.read_bytes(), original_source)
            self.assertEqual(other_zip.read_bytes(), b'other engine archive')
            self.assertEqual({file.relative_to(other): file.read_bytes() for file in other.rglob('*') if file.is_file()},
                             other_files)

    def test_compression_cleanup_zip_failure_preserves_old_output(self):
        self.payload(self.final, version='5.4.3')
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        original_files = {file.relative_to(self.final): file.read_bytes()
                          for file in self.final.rglob('*') if file.is_file()}
        with patch('Source.Logic.Packaging.BuildRunner') as runner, patch(
                'Source.Logic.Packaging.WriteSourceZip', side_effect=OSError('zip failed')):
            self.runner(runner)
            with self.assertRaisesRegex(OSError, 'zip failed'):
                self.run_job(BuildOptions('deploy', Zip=True, DeleteOutput=True))
        self.assertEqual(self.archive.read_bytes(), original_zip)
        self.assertEqual({file.relative_to(self.final): file.read_bytes()
                          for file in self.final.rglob('*') if file.is_file()}, original_files)

    def test_compression_cleanup_publish_failure_restores_old_output_and_zip(self):
        from Source.Logic.PackagingPaths import RenameSibling

        self.payload(self.final, version='5.4.3')
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        original_files = {file.relative_to(self.final): file.read_bytes()
                          for file in self.final.rglob('*') if file.is_file()}

        def fail_publish(source, destination, *identity):
            if source.name.endswith('-new.zip'):
                raise OSError('zip publish failed')
            return RenameSibling(source, destination, *identity)

        with patch('Source.Logic.Packaging.BuildRunner') as runner, patch(
                'Source.Logic.Packaging.RenameSibling', side_effect=fail_publish):
            self.runner(runner)
            with self.assertRaisesRegex(OSError, 'zip publish failed'):
                self.run_job(BuildOptions('deploy', Zip=True, DeleteOutput=True))
        self.assertEqual(self.archive.read_bytes(), original_zip)
        self.assertEqual({file.relative_to(self.final): file.read_bytes()
                          for file in self.final.rglob('*') if file.is_file()}, original_files)
        self.assertFalse((self.final.parent / '.5.4.transaction').exists())

    def test_compression_cleanup_refuses_output_inside_other_source_plugin(self):
        output = self.source.parent.parent / 'OtherPlugin'
        with patch('Source.Logic.Packaging.BuildRunner') as runner:
            with self.assertRaisesRegex(ValueError, '重叠|包含'):
                RunPackaging(self.engine, [self.engine], 'Example', self.source, output,
                             BuildOptions('deploy', Zip=True, DeleteOutput=True), Log=lambda line: None)
        runner.assert_not_called()
        self.assertFalse(output.exists())

    def test_compression_cleanup_refuses_replaced_output_without_deleting_it(self):
        from Source.Logic.Packaging import CommitArtifacts
        from Source.Logic.PackagingPaths import RenameSibling

        self.payload(self.final, version='5.4.3')
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        displaced = self.final.with_name('displaced-original')

        def replace_output(stage, items, **options):
            RenameSibling(self.final, displaced)
            self.final.mkdir()
            (self.final / 'unrelated.txt').write_bytes(b'not a build artifact')
            return CommitArtifacts(stage, items, **options)

        with patch('Source.Logic.Packaging.BuildRunner') as runner, patch(
                'Source.Logic.Packaging.CommitArtifacts', side_effect=replace_output):
            self.runner(runner)
            with self.assertRaisesRegex(ValueError, '变化'):
                self.run_job(BuildOptions('deploy', Zip=True, DeleteOutput=True))
        self.assertEqual(self.archive.read_bytes(), original_zip)
        self.assertEqual((self.final / 'unrelated.txt').read_bytes(), b'not a build artifact')
        self.assertTrue((displaced / 'Example.uplugin').is_file())
        self.assertTrue((self.final.parent / '.5.4.transaction').is_dir())

    def test_compression_cleanup_cancel_before_commit_preserves_output(self):
        from Source.Logic import Packaging

        self.payload(self.final, version='5.4.3')
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        gate = Packaging.CancelGate()
        check = Packaging._CheckSourceOptions
        calls = []

        def cancel_at_preflight(*args):
            check(*args)
            calls.append(True)
            if len(calls) == 4:
                gate.Stop()

        with patch.object(Packaging, '_CheckSourceOptions', side_effect=cancel_at_preflight), patch.object(
                Packaging, 'BuildRunner') as runner:
            self.runner(runner)
            with self.assertRaises(Packaging.PackagingCancelled):
                Packaging.RunPackaging(self.engine, [self.engine], 'Example', self.source, self.output,
                                       BuildOptions('deploy', Zip=True, DeleteOutput=True),
                                       Gate=gate, Log=lambda line: None)
        self.assertEqual(self.archive.read_bytes(), original_zip)
        self.assertTrue((self.final / 'Example.uplugin').is_file())

    def test_compression_cleanup_failure_retains_backup_after_zip_is_committed(self):
        from Source.Logic.Packaging import _RemoveStage

        self.payload(self.final, version='5.4.3')

        def refuse_old_cleanup(stage, parent, expected):
            if stage.name.endswith('-old-package'):
                raise OSError('backup locked')
            return _RemoveStage(stage, parent, expected)

        with patch('Source.Logic.Packaging.BuildRunner') as runner, patch(
                'Source.Logic.Packaging._RemoveStage', side_effect=refuse_old_cleanup):
            self.runner(runner)
            with self.assertRaisesRegex(RuntimeError, '产物已提交.*清理'):
                self.run_job(BuildOptions('deploy', Zip=True, DeleteOutput=True))
        self.assertFalse(self.final.exists())
        with zipfile.ZipFile(self.archive) as archive:
            self.assertIsNone(archive.testzip())
        self.assertTrue((self.final.parent / '.5.4.transaction-old-package/Example.uplugin').is_file())
        self.assertTrue((self.final.parent / '.5.4.transaction/commit.json').is_file())

    def test_compression_cleanup_rejects_engine_path_retargeting_and_unknown_old_version(self):
        self.payload(self.final, version='5.4.3')
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        version_file = Path(self.engine['Path']) / 'Engine/Build/Build.version'
        version_file.write_text(json.dumps({'MajorVersion': 5, 'MinorVersion': 7, 'PatchVersion': 1}))
        descriptor = self.final / 'Example.uplugin'
        original_descriptor = descriptor.read_bytes()
        with patch('Source.Logic.Packaging.BuildRunner') as runner:
            with self.assertRaisesRegex(ValueError, '版本不匹配'):
                self.run_job(BuildOptions('deploy', Zip=True, DeleteOutput=True))
        runner.assert_not_called()
        self.assertEqual(descriptor.read_bytes(), original_descriptor)
        self.assertEqual(self.archive.read_bytes(), original_zip)
        self.assertFalse(self.archive.with_name('Example_UE_5.7_Source.zip').exists())
        fields = json.loads(descriptor.read_text())
        del fields['EngineVersion']
        descriptor.write_text(json.dumps(fields))
        unknown_descriptor = descriptor.read_bytes()
        with patch('Source.Logic.Packaging.BuildRunner') as runner:
            with self.assertRaisesRegex(ValueError, '无法确认.*版本'):
                self.run_job(BuildOptions('deploy', Zip=True, DeleteOutput=True))
        runner.assert_not_called()
        self.assertEqual(descriptor.read_bytes(), unknown_descriptor)
        self.assertEqual(self.archive.read_bytes(), original_zip)

    def test_deploy_refuses_wrong_engine_build_id(self):
        engine_manifest = Path(self.engine['Path']) / 'Engine/Binaries/Win64/UnrealEditor.modules'
        engine_manifest.write_text(json.dumps({'BuildId': 'wrong', 'Modules': {}}))
        with patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            with self.assertRaisesRegex(ValueError, 'BuildId'):
                self.run_job(BuildOptions('deploy'))
        self.assertFalse(self.final.exists())

    def test_deploy_requires_manifest_mapping_but_skips_denied_module(self):
        original_payload = self.payload

        def mismatched_payload(destination):
            original_payload(destination)
            descriptor = destination / 'Example.uplugin'
            fields = json.loads(descriptor.read_text())
            fields['Modules'].append({'Name': 'OtherPlatform', 'PlatformDenyList': ['Win64']})
            descriptor.write_text(json.dumps(fields))
            manifest = destination / 'Binaries/Win64/UnrealEditor.modules'
            manifest.write_text(json.dumps({'BuildId': 'example', 'Modules': {'Example': 'Other.dll'}}))

        with patch.object(self, 'payload', mismatched_payload), patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            with self.assertRaisesRegex(ValueError, '映射'):
                self.run_job(BuildOptions('deploy'))
            invalid_payload = self.payload

            def restore_mapping(destination):
                invalid_payload(destination)
                manifest = destination / 'Binaries/Win64/UnrealEditor.modules'
                manifest.write_text(json.dumps({'BuildId': 'example', 'Modules': {'Example': 'UnrealEditor-Example.dll'}}))

            with patch.object(self, 'payload', restore_mapping):
                self.run_job(BuildOptions('deploy'))
        self.assertTrue(self.final.exists())

    def test_unconfirmed_process_tree_retains_stage_and_blocks_publish(self):
        job = Mock(Confirmed=False, Handle=123)
        job.__enter__ = Mock(return_value=job)
        job.__exit__ = Mock(return_value=False)
        job.Launch.side_effect = RuntimeError('job state unavailable')
        with patch('Source.Logic.BuildRunner.WindowsJob', return_value=job):
            with self.assertRaisesRegex(RuntimeError, 'job state unavailable'):
                self.run_job()
        self.assertTrue((self.final.with_name('.5.4.transaction') / 'running.json').is_file())
        self.assertFalse(self.final.exists())
        with self.assertRaisesRegex(RuntimeError, '未完成事务'):
            self.run_job(zip_only=True)

    def test_explicit_filtered_library_and_vendor_survive_source_zip(self):
        original_payload = self.payload
        files = {'Source/Vendor/libraries.lib': b'unchanged', 'Vendor/support.dll': b'unchanged',
                 'Extras/special.dll': b'unchanged', 'Config/FilterPlugin.ini': b'[FilterPlugin]\n/Extras/...\n',
                 'Config/FilterPluginWin64.ini': b'[FilterPlugin]\n/PlatformDeps/...\n',
                 'PlatformDeps/win64.lib': b'platform library'}

        def add_dependencies(destination):
            for name, content in files.items():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)

        def with_dependencies(destination):
            original_payload(destination)
            add_dependencies(destination)
            (destination / 'Config/FilterPluginWin64.ini').write_text('[FilterPlugin]\n-/PlatformDeps/...\n')

        add_dependencies(self.source.parent)
        stale = self.source.parent / 'Binaries/Win64/UnrealEditor-Unregistered.dll'
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b'old local build')
        with patch.object(self, 'payload', with_dependencies), patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            self.run_job(BuildOptions('fab'))
        self.assertEqual(stale.read_bytes(), b'old local build')
        self.assertFalse((self.final / stale.relative_to(self.source.parent)).exists())
        with zipfile.ZipFile(self.archive) as archive:
            for name, content in files.items():
                self.assertEqual(archive.read('Example/' + name), content)

    def test_vendor_input_loss_refuses_publish_without_touching_source(self):
        vendor = self.source.parent / 'Source/Vendor/library.lib'
        vendor.parent.mkdir(parents=True)
        vendor.write_bytes(b'vendor')
        with patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            with self.assertRaisesRegex(ValueError, 'library.lib'):
                self.run_job()
        self.assertEqual(vendor.read_bytes(), b'vendor')
        self.assertFalse(self.final.exists())

    def test_fab_rejects_invalid_link_but_legacy_accepts(self):
        original_payload = self.payload

        def invalid_payload(destination):
            original_payload(destination)
            descriptor = destination / 'Example.uplugin'
            fields = json.loads(descriptor.read_text())
            fields['MarketplaceURL'] = 'not a launcher URL'
            descriptor.write_text(json.dumps(fields))

        with patch.object(self, 'payload', invalid_payload), patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            with self.assertRaisesRegex(ValueError, 'Launcher'):
                self.run_job(BuildOptions('fab'))
            self.run_job()
        self.assertTrue(self.final.exists())

    def test_fab_restores_source_only_fab_url_after_uat_strips_it(self):
        original_payload = self.payload
        fields = json.loads(self.source.read_bytes())
        link = 'com.epicgames.launcher://ue/Fab/product/12345678-1234-1234-1234-123456789abc'
        fields['FabURL'] = link
        original = json.dumps(fields).encode()
        self.source.write_bytes(original)

        def stripped_payload(destination):
            original_payload(destination)
            descriptor = destination / 'Example.uplugin'
            fields = json.loads(descriptor.read_bytes())
            fields['MarketplaceURL'] = ''
            descriptor.write_text(json.dumps(fields))

        with patch.object(self, 'payload', stripped_payload), patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            self.run_job(BuildOptions('fab'))
        self.assertEqual(self.source.read_bytes(), original)
        with zipfile.ZipFile(self.archive) as archive:
            fields = json.loads(archive.read('Example/Example.uplugin'))
            self.assertEqual((fields['FabURL'], fields['MarketplaceURL']), (link, link))

    def test_fab_skips_module_with_explicit_empty_platform_allow_list(self):
        from Source.Logic.Packaging import _Win64Modules

        fields = {'Modules': [{'Name': 'NotWin64', 'PlatformAllowList': []},
                              {'Name': 'Legacy', 'WhitelistPlatforms': []},
                              {'Name': 'Win64Module', 'PlatformDenyList': ['Linux']}]}
        for check_fab in (False, True):
            self.assertEqual(list(_Win64Modules(fields, CheckFab=check_fab)), ['win64module'])

    def test_generated_filter_preserves_vendor_binary_rule_in_zip(self):
        original_payload = self.payload
        dependency = Path('Binaries/Win64/vendor.dll')
        rules = Path('Config/FilterPlugin.ini')

        def payload(destination):
            original_payload(destination)
            (destination / dependency).write_bytes(b'vendor binary')

        for path, content in ((dependency, b'vendor binary'),
                              (rules, b'[FilterPlugin]\n/Binaries/Win64/vendor.dll\n')):
            target = self.source.parent / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        settings = Mock(Get=Mock(return_value={'自动生成FilterPlugin.ini': True}))
        with patch('Source.Logic.PostProcessor.ConfigManager', return_value=settings), \
                patch.object(self, 'payload', payload), patch('Source.Logic.Packaging.BuildRunner') as runner:
            self.runner(runner)
            self.run_job(BuildOptions('fab'))
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual(archive.read('Example/' + dependency.as_posix()), b'vendor binary')
            self.assertIn(b'/Binaries/Win64/vendor.dll', archive.read('Example/' + rules.as_posix()))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows rename handle')
    def test_commit_entry_rejects_replaced_new_zip_after_final_preflight(self):
        from Source.Logic.Packaging import CommitArtifacts
        from Source.Logic.PackagingPaths import RenameSibling

        self.payload(self.final)
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        swapped = self.archive.with_name('.displaced-new.zip')

        def replace_new(stage, items, **options):
            pending = items[0][0]
            RenameSibling(pending, swapped)
            pending.write_bytes(b'unvalidated replacement')
            return CommitArtifacts(stage, items, **options)

        with patch('Source.Logic.Packaging.CommitArtifacts', side_effect=replace_new):
            with self.assertRaisesRegex(ValueError, '暂存件.*变化'):
                self.run_job(zip_only=True)
        self.assertEqual(self.archive.read_bytes(), original_zip)
        self.assertTrue(zipfile.is_zipfile(swapped))
        self.assertTrue((self.final.parent / '.5.4.transaction').is_dir())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows rename handle')
    def test_commit_refuses_replaced_ordinary_leaf_and_retains_journal(self):
        from Source.Logic.Packaging import ArtifactIdentity, CommitArtifacts
        from Source.Logic.PackagingPaths import RenameSibling

        stage = self.root / 'stage'
        stage.mkdir()
        pending, final, backup, displaced = (self.root / name for name in ('pending', 'final', 'backup', 'displaced'))
        final.write_bytes(b'old')
        pending.write_bytes(b'new')

        def replace_old(source, destination, *identity):
            if source == final:
                RenameSibling(source, displaced)
                source.write_bytes(b'unrelated replacement')
            return RenameSibling(source, destination, *identity)

        with patch('Source.Logic.Packaging.RenameSibling', side_effect=replace_old):
            with self.assertRaises(ValueError):
                CommitArtifacts(stage, [(pending, final, backup, ArtifactIdentity(final))])
        self.assertTrue((stage / 'commit.json').is_file())
        self.assertFalse(backup.exists())
        self.assertEqual(final.read_bytes(), b'unrelated replacement')
        self.assertEqual(displaced.read_bytes(), b'old')

    def test_cancel_during_last_preflight_never_publishes(self):
        from Source.Logic.Packaging import CancelGate, PackagingCancelled
        from Source.Logic import Packaging

        gate = CancelGate()
        original = Packaging._CheckSourceOptions
        calls = []

        def preflight(*args):
            original(*args)
            calls.append(True)
            if len(calls) == 4:
                self.assertFalse(gate.Stop())

        with patch.object(Packaging, '_CheckSourceOptions', side_effect=preflight), patch.object(
                Packaging, 'BuildRunner') as runner:
            self.runner(runner)
            with self.assertRaises(PackagingCancelled):
                RunPackaging(self.engine, [self.engine], 'Example', self.source, self.output,
                             BuildOptions(), Gate=gate, Log=lambda line: None)
        self.assertFalse(self.final.exists())

    def test_zip_only_preserves_output_and_checks_members(self):
        self.payload(self.final)
        descriptor = self.final / 'Example.uplugin'
        original = descriptor.read_bytes()
        with patch('Source.Logic.Packaging.BuildRunner') as Runner:
            self.run_job(zip_only=True)
            Runner.assert_not_called()
        with zipfile.ZipFile(self.archive) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            for member in ('Source/Tests/Test.cpp', 'Shaders/code.usf', 'Binaries/ThirdParty/Vendor/vendor.dll'):
                self.assertIn('Example/' + member, names)
            self.assertTrue(all(name.startswith('Example/') for name in names))
            self.assertFalse(any(token in name for name in names for token in (
                'Example/Tests/', 'Intermediate/', '.git/', '.codex/', 'UnrealEditor-Example.',
                'UnrealEditor.modules')))
            manifest = json.loads(archive.read('Example/Example.uplugin'))
            self.assertEqual(manifest['EngineVersion'], '5.4.3')
            self.assertEqual(manifest['FabURL'], manifest['MarketplaceURL'])
        self.assertEqual(descriptor.read_bytes(), original)

    def test_zip_refuses_shell_failure_marker_and_unknown_binary(self):
        self.final.mkdir(parents=True)
        (self.final / 'Example.uplugin').write_text(json.dumps({'FileVersion': 3}))
        with self.assertRaisesRegex(Exception, '载荷'):
            self.run_job(zip_only=True)
        self.payload(self.final)
        (self.final / 'Failed.log').touch()
        with self.assertRaisesRegex(Exception, 'Failed.log'):
            self.run_job(zip_only=True)
        (self.final / 'Failed.log').unlink()
        (self.final / 'Binaries/Win64/unknown.dll').touch()
        with self.assertRaisesRegex(Exception, 'unknown.dll'):
            self.run_job(zip_only=True)
        self.assertFalse(self.archive.exists())

    def test_stage_and_post_failure_leave_old_outputs(self):
        self.payload(self.final)
        self.run_job(zip_only=True)
        original = self.archive.read_bytes()
        with patch('Source.Logic.Packaging.BuildRunner') as Runner:
            Runner.return_value.RunBuild.return_value = iter(['EXIT_FAILURE'])
            with self.assertRaises(RuntimeError):
                self.run_job(BuildOptions('fab'))
            self.runner(Runner)
            with patch('Source.Logic.Packaging.RunPostProcess', return_value=['❌ failed']):
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    self.run_job(BuildOptions('fab'))
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertFalse((self.final / 'Failed.log').exists())
        self.assertTrue(list(self.final.parent.glob('*.failed-*.log')))

    def test_zip_commit_failure_rolls_back_directory_and_zip(self):
        from Source.Logic.PackagingPaths import RenameSibling

        self.payload(self.final)
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        original_manifest = (self.final / 'Example.uplugin').read_bytes()
        def fail_zip(source, destination, identity):
            if Path(source).name.endswith('-new.zip') and Path(destination) == self.archive:
                raise OSError('injected ZIP rename failure')
            RenameSibling(source, destination, identity)

        with patch('Source.Logic.Packaging.BuildRunner') as Runner:
            self.runner(Runner)
            with patch('Source.Logic.Packaging.RenameSibling', side_effect=fail_zip):
                with self.assertRaisesRegex(OSError, 'injected'):
                    self.run_job(BuildOptions('fab'))
        self.assertEqual(self.archive.read_bytes(), original_zip)
        self.assertEqual((self.final / 'Example.uplugin').read_bytes(), original_manifest)

    def test_failed_rollback_keeps_transaction_and_blocks_zip_only(self):
        from Source.Logic.PackagingPaths import RenameSibling

        self.payload(self.final)
        self.run_job(zip_only=True)
        def fail_commit_and_rollback(source, destination, identity):
            if Path(source).name.endswith(('-new.zip', '-old.zip')):
                raise OSError('injected rename failure')
            RenameSibling(source, destination, identity)

        with patch('Source.Logic.Packaging.BuildRunner') as Runner:
            self.runner(Runner)
            with patch('Source.Logic.Packaging.RenameSibling', side_effect=fail_commit_and_rollback):
                with self.assertRaisesRegex(RuntimeError, '回滚失败'):
                    self.run_job(BuildOptions('fab'))
        transaction = self.final.with_name('.5.4.transaction')
        self.assertTrue((transaction / 'commit.json').is_file())
        self.assertTrue((transaction.with_name(transaction.name + '-old-package') / 'Example.uplugin').is_file())
        self.assertTrue(transaction.with_name(transaction.name + '-old.zip').is_file())
        with self.assertRaisesRegex(RuntimeError, '未完成事务'):
            self.run_job(zip_only=True)

    def test_no_zip_leaves_existing_archive_untouched(self):
        self.final.parent.mkdir(parents=True)
        self.archive.write_bytes(b'untouched ZIP')
        with patch('Source.Logic.Packaging.BuildRunner') as Runner:
            self.runner(Runner)
            artifacts = self.run_job(BuildOptions('fab', False))
        self.assertEqual(artifacts, (self.final,))
        self.assertEqual(self.archive.read_bytes(), b'untouched ZIP')

    def test_interrupt_during_commit_preserves_recovery_record(self):
        from Source.Logic.PackagingPaths import RenameSibling

        self.payload(self.final)
        self.run_job(zip_only=True)
        def interrupt_commit(source, destination, identity):
            if Path(source).name.endswith('-new.zip'):
                raise KeyboardInterrupt()
            RenameSibling(source, destination, identity)

        with patch('Source.Logic.Packaging.BuildRunner') as Runner:
            self.runner(Runner)
            with patch('Source.Logic.Packaging.RenameSibling', side_effect=interrupt_commit):
                with self.assertRaises(KeyboardInterrupt):
                    self.run_job(BuildOptions('fab'))
        transaction = self.final.with_name('.5.4.transaction')
        self.assertTrue((transaction / 'commit.json').is_file())
        self.assertTrue(transaction.with_name(transaction.name + '-old.zip').is_file())
        self.assertTrue((transaction.with_name(transaction.name + '-old-package') / 'Example.uplugin').is_file())

    def test_zip_refuses_disagreeing_urls_without_replacing_old_zip(self):
        self.payload(self.final)
        self.run_job(zip_only=True)
        original_zip = self.archive.read_bytes()
        descriptor = self.final / 'Example.uplugin'
        fields = json.loads(descriptor.read_text())
        fields['FabURL'] = 'different'
        descriptor.write_text(json.dumps(fields))
        with self.assertRaisesRegex(ValueError, '不一致'):
            self.run_job(zip_only=True)
        self.assertEqual(self.archive.read_bytes(), original_zip)

    def test_overlap_and_case_alias_rejected_before_build(self):
        original = self.output
        for unsafe in (self.source.parent, self.root, Path(self.engine['Path']) / 'out'):
            self.output = unsafe
            with self.assertRaisesRegex(ValueError, '重叠'):
                self.run_job()
        self.output = original
        self.payload(self.final)
        with self.assertRaises(ValueError):
            RunPackaging(self.engine, [self.engine], 'example', self.source, self.output, BuildOptions())
        other_engine = {'Name': 'UE 5.6 源码', 'Path': str(self.output.parent)}
        with self.assertRaisesRegex(ValueError, '重叠'):
            RunPackaging(self.engine, [self.engine, other_engine], 'Example', self.source,
                         self.output, BuildOptions())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction')
    def test_junction_rejected_before_following_target(self):
        self.final.parent.mkdir(parents=True)
        result = subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(self.final), str(self.source.parent)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            with self.assertRaises(ValueError):
                self.run_job()
        finally:
            self.final.rmdir()

    def test_lock_conflict(self):
        self.payload(self.final)
        with TargetLock(self.final.parent):
            result = subprocess.run([sys.executable, '-B', '-c',
                                     'import sys; from pathlib import Path; '
                                     'from Source.Logic.Packaging import TargetLock; '
                                     'TargetLock(Path(sys.argv[1])).__enter__()', str(self.final.parent)],
                                    capture_output=True, encoding='utf-8', errors='replace',
                                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('打包目标锁被占用', result.stderr)

    def test_profile_and_cli(self):
        self.assertTrue(BuildOptions('fab').MakeZip)
        self.assertFalse(BuildOptions('deploy').MakeZip)
        self.assertFalse(BuildOptions('fab', False).MakeZip)
        self.assertEqual(ParseArgs(['zip', 'Example', '--all']).command, 'zip')
        self.assertIsNone(ParseArgs(['build', 'Example']).profile)
        for arguments in (['--zip', '--no-zip'], ['--profile', 'fab', '--keep-binaries'],
                          ['--profile', 'deploy', '--no-post']):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                ParseArgs(['build', 'Example'] + arguments)
            self.assertEqual(error.exception.code, 2)
