import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Source.Logic.ConfigManager import ConfigManager
from Source.Logic.PostProcessor import AddCopyrightHeaders, RunPostProcess


class PostProcessorTests(unittest.TestCase):
    def _CreatePlugin(self, Root: Path) -> Path:
        PluginDir = Root / "UnicodePlugin"
        (PluginDir / "Source" / "UnicodePlugin" / "Private").mkdir(parents=True)
        (PluginDir / "UnicodePlugin.uplugin").write_text(
            json.dumps(
                {
                    "CreatedBy": "Test Author",
                    "MarketplaceURL": "com.epicgames.launcher://ue/marketplace/product/test",
                }
            ),
            encoding="utf-8",
        )
        return PluginDir

    def test_add_copyright_preserves_utf8_unicode_after_ascii_prefix(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            Original = (
                "// " + "ASCII prefix " * 220 + "\n"
                "// 中文注释：保留中文标点。\n"
                "const TCHAR* Message = TEXT(\"ambiguous — match → target\");\n"
                "// English text remains unchanged.\n"
            )
            SourcePath.write_text(Original, encoding="utf-8", newline="")

            Logs = AddCopyrightHeaders(str(PluginDir), "Test Author")

            Expected = "// Copyright (c) 2025 Test Author. All rights reserved.\n\n" + Original
            self.assertEqual(SourcePath.read_bytes(), Expected.encode("utf-8"))
            self.assertFalse(any("失败" in Line for Line in Logs))

    def test_copyright_replacement_preserves_utf8_bom_and_crlf(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            OriginalBody = "// 中文注释：标点，箭头 →，破折号 —\r\nint Value = 1;\r\n"
            SourcePath.write_text(
                "// Copyright 2020 Previous Author\r\n\r\n" + OriginalBody,
                encoding="utf-8-sig",
                newline="",
            )

            AddCopyrightHeaders(str(PluginDir), "Test Author")

            Expected = (
                "// Copyright (c) 2025 Test Author. All rights reserved.\r\n\r\n" + OriginalBody
            )
            self.assertEqual(SourcePath.read_bytes(), b"\xef\xbb\xbf" + Expected.encode("utf-8"))

    def test_non_copyright_leading_comment_is_preserved(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            Original = "// 中文版权说明之外的注释。\n// Arrow → and dash —.\n\nint Value = 1;\n"
            SourcePath.write_text(Original, encoding="utf-8", newline="")

            AddCopyrightHeaders(str(PluginDir), "Test Author")

            Expected = "// Copyright (c) 2025 Test Author. All rights reserved.\n\n" + Original
            self.assertEqual(SourcePath.read_bytes(), Expected.encode("utf-8"))

    def test_full_line_block_copyright_is_replaced(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            SourcePath.write_text(
                "/* Copyright 2020 Previous Author */\n\n// 中文 → —\nint Value = 1;\n",
                encoding="utf-8",
                newline="",
            )

            AddCopyrightHeaders(str(PluginDir), "Test Author")

            Expected = (
                "// Copyright (c) 2025 Test Author. All rights reserved.\n\n"
                "// 中文 → —\nint Value = 1;\n"
            )
            self.assertEqual(SourcePath.read_bytes(), Expected.encode("utf-8"))

    def test_block_comment_with_trailing_code_is_preserved(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            Original = "/* Copyright 2020 */ int Value = 1;\n// 中文 → —\n"
            SourcePath.write_text(Original, encoding="utf-8", newline="")

            AddCopyrightHeaders(str(PluginDir), "Test Author")

            Expected = "// Copyright (c) 2025 Test Author. All rights reserved.\n\n" + Original
            self.assertEqual(SourcePath.read_bytes(), Expected.encode("utf-8"))

    def test_unclosed_block_comment_is_preserved(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            Original = "/* Copyright 2020\n// 中文 → —\nint Value = 1;\n"
            SourcePath.write_text(Original, encoding="utf-8", newline="")

            AddCopyrightHeaders(str(PluginDir), "Test Author")

            Expected = "// Copyright (c) 2025 Test Author. All rights reserved.\n\n" + Original
            self.assertEqual(SourcePath.read_bytes(), Expected.encode("utf-8"))

    def test_post_process_keeps_source_bytes_when_copyright_is_disabled(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            OriginalBytes = "// 中文，—，→ and English\n".encode("utf-8")
            SourcePath.write_bytes(OriginalBytes)
            Settings = {
                "自动添加版权声明": False,
                "转换MarketplaceURL为FabURL": True,
                "删除Binaries文件夹": False,
                "删除Intermediate文件夹": False,
                "自动生成FilterPlugin.ini": False,
            }

            with patch.object(ConfigManager, "Get", return_value=Settings):
                RunPostProcess(str(PluginDir))

            self.assertEqual(SourcePath.read_bytes(), OriginalBytes)
            Manifest = (PluginDir / "UnicodePlugin.uplugin").read_text(encoding="utf-8")
            self.assertIn('"FabURL"', Manifest)
            self.assertNotIn('"MarketplaceURL"', Manifest)

    def test_post_process_keeps_binaries_and_fab_features(self):
        with tempfile.TemporaryDirectory() as TempDir:
            PluginDir = self._CreatePlugin(Path(TempDir))
            SourcePath = PluginDir / "Source" / "UnicodePlugin" / "Private" / "UnicodeText.cpp"
            SourcePath.write_text("// 中文。Unicode — → English\n", encoding="utf-8")
            BinaryPath = PluginDir / "Binaries" / "Win64" / "UnicodePlugin.dll"
            BinaryPath.parent.mkdir(parents=True)
            BinaryPath.write_bytes(b"binary")
            (PluginDir / "Intermediate").mkdir()
            Settings = {
                "自动添加版权声明": True,
                "转换MarketplaceURL为FabURL": True,
                "删除Binaries文件夹": True,
                "删除Intermediate文件夹": True,
                "自动生成FilterPlugin.ini": True,
            }

            with patch.object(ConfigManager, "Get", return_value=Settings):
                Logs = RunPostProcess(str(PluginDir), KeepBinaries=True)

            self.assertTrue(BinaryPath.is_file())
            self.assertFalse((PluginDir / "Intermediate").exists())
            self.assertTrue((PluginDir / "Config" / "FilterPlugin.ini").is_file())
            self.assertIn("中文。Unicode — → English", SourcePath.read_text(encoding="utf-8"))
            self.assertTrue(any("保留 Binaries" in Line for Line in Logs))


if __name__ == "__main__":
    unittest.main()
