import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

PACK = Path(__file__).resolve().parents[1]
runtime_spec = importlib.util.spec_from_file_location('book_runtime_test', PACK/'runtime.py')
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)
COMFY = Path(runtime.settings()['comfyui'])
sys.path.insert(0, str(COMFY))
package = types.ModuleType("book_test_pack")
package.__path__ = [str(PACK)]
sys.modules[package.__name__] = package
story = importlib.import_module("book_test_pack.story")
storage = importlib.import_module("book_test_pack.storage")
render = importlib.import_module("book_test_pack.render")
export = importlib.import_module("book_test_pack.export")


def fixture():
    return {
        "title": "The Borrowed Moonlight", "summary": "A child and two friends share the light.",
        "visual_bible": {"style": "soft gouache", "palette": "gold and blue", "world": "a moonlit garden"},
        "style_reference_prompt": "An empty moonlit garden, without people or animals.",
        "characters": [
            {"id": "mira", "name": "Mira", "role": "main", "appearance": "A child with black curls and a red coat.", "personality": "kind"},
            {"id": "pip", "name": "Pip", "role": "supporting", "appearance": "A small grey mouse with a blue scarf.", "personality": "curious"},
            {"id": "fern", "name": "Fern", "role": "supporting", "appearance": "A brown rabbit wearing a green waistcoat.", "personality": "patient"},
        ],
        "cover": {"scene_prompt": "Mira and Pip look at the moon.", "character_ids": ["mira", "pip"]},
        "pages": [
            {"page_number": 1, "text": "Mira found a ribbon of moonlight in the garden.", "scene_prompt": "Mira finds a ribbon of light.", "character_ids": ["mira"]},
            {"page_number": 2, "text": "Mira, Pip and Fern shared the light.", "scene_prompt": "The three friends share the light.", "character_ids": ["mira", "pip", "fern"]},
            {"page_number": 3, "text": "The empty garden glowed softly all night.", "scene_prompt": "An empty glowing garden.", "character_ids": []},
        ],
    }


def package_fixture():
    book = fixture()
    names = {c["id"]: c["name"] for c in book["characters"]}
    canonical = {
        "id": "story_test_001",
        "pages": [{"text": p["text"], "pageNumber": p["page_number"], "imagePrompt": p["scene_prompt"],
                   "charactersPresent": [names[cid] for cid in p["character_ids"]],
                   "isMainCharacterPresent": "mira" in p["character_ids"]} for p in book["pages"]],
        "metadata": {
            "theme": "Sharing", "title": book["title"], "ageRange": "4-6", "characters": list(names.values()),
            "bookSummary": book["summary"], "storyPrompt": "Friends share moonlight.",
            "coverImagePrompt": book["cover"]["scene_prompt"], "styleReferencePrompt": "soft gouache, gold and blue",
            "mainCharacterDescriptivePrompt": book["characters"][0]["appearance"],
        },
    }
    production = {k: book[k] for k in ("visual_bible", "style_reference_prompt", "characters")}
    production["cover_character_ids"] = book["cover"]["character_ids"]
    return {"story": canonical, "production": production}


class BookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)
        fake = types.ModuleType("folder_paths")
        fake.get_output_directory = lambda: str(self.output)
        self.previous = sys.modules.get("folder_paths")
        sys.modules["folder_paths"] = fake
        self.addCleanup(self.restore_module)
        self.project = {"book": fixture(), "config": {"seed": 100, "art_style": story.DEFAULT_STYLE},
                        **package_fixture(),
                        "render_root": str(self.output / "codex/books/test/renders/test"),
                        "render_settings": {**render.DEFAULT_MODELS, "image_steps": 8, "edit_steps": 40, "edit_cfg": 4.0}}

    def restore_module(self):
        if self.previous is None:
            sys.modules.pop("folder_paths", None)
        else:
            sys.modules["folder_paths"] = self.previous

    def test_valid_story_and_semantic_failures(self):
        story.validate_book(fixture(), 3, 3)
        for change in (lambda b: b["pages"][0].update(page_number=2),
                       lambda b: b["pages"][0].update(character_ids=["unknown"]),
                       lambda b: b["characters"][1].update(id="mira"),
                       lambda b: b["characters"][1].update(role="main"),
                       lambda b: b["pages"][0].update(text="word " * 101)):
            bad = fixture()
            change(bad)
            with self.assertRaises(ValueError):
                story.validate_book(bad, 3, 3)

    def test_reference_routing_and_stable_seeds(self):
        for count in range(4):
            scene = {"scene_prompt": "A scene", "character_ids": ["mira", "pip", "fern"][:count]}
            refs = story.scene_references(self.project, scene)
            self.assertLessEqual(len(refs), 3)
            self.assertEqual("style.png" in refs, count < 3)
            self.assertEqual(refs[:count], [f"characters/{cid}.png" for cid in scene["character_ids"]])
        specs = story.asset_specs(self.project)
        self.assertEqual(len(specs), 8)
        self.assertEqual(len({s["seed"] for s in specs}), len(specs))
        self.assertEqual(specs, story.asset_specs(copy.deepcopy(self.project)))
        self.assertEqual(specs[-1]["references"], ["style.png"])

    def test_cover_prompt_requests_exact_title_typography_but_pages_stay_unlettered(self):
        specs = story.asset_specs(self.project)
        cover = next(s for s in specs if s['name'] == 'cover.png')
        page = next(s for s in specs if s['name'] == 'pages/page-001.png')
        self.assertIn('"The Borrowed Moonlight"', cover['prompt'])
        self.assertIn('readable lettering', cover['prompt'])
        self.assertIn('display font', cover['prompt'])
        self.assertIn('clear negative space', cover['prompt'])
        self.assertIn('No text, captions', page['prompt'])
        self.assertNotIn('The Borrowed Moonlight', page['prompt'])

    def test_original_app_contract_is_preserved(self):
        original_path = COMFY / "user/default/workflows/childrens-book-generator.json"
        workflow = json.loads(original_path.read_text())
        original = json.loads(next(n for n in workflow["nodes"] if n["id"] == 119)["widgets_values"][0])
        story.validate_story(original, 12, 6)
        package = package_fixture()
        before = copy.deepcopy(package["story"])
        story.validate_package(package, 3, 3)
        self.assertEqual(package["story"], before)
        self.assertEqual(set(before), set(original))
        self.assertEqual(set(before["metadata"]), set(original["metadata"]))
        self.assertEqual(set(before["pages"][0]), set(original["pages"][0]))
        bad = copy.deepcopy(package)
        bad["story"]["pages"][0]["isMainCharacterPresent"] = False
        with self.assertRaises(ValueError):
            story.validate_package(bad, 3, 3)
        bad = copy.deepcopy(package)
        bad["story"]["metadata"]["reference_files"] = []
        with self.assertRaises(ValueError):
            story.validate_package(bad, 3, 3)

    def test_unsafe_paths_and_no_overwrite(self):
        for bad in ("../evil.png", "/tmp/evil.png", "characters/../../evil.png"):
            with self.assertRaises(ValueError):
                storage.asset_path(self.project, bad)
        path = self.output / "record.txt"
        storage.write_exclusive(path, b"original")
        storage.write_exclusive(path, b"original")
        with self.assertRaises(FileExistsError):
            storage.write_exclusive(path, b"replacement")
        self.assertEqual(path.read_bytes(), b"original")
        root = storage.checked_root(self.project)
        root.mkdir(parents=True)
        (root / "characters").symlink_to(self.output)
        with self.assertRaises(ValueError):
            storage.asset_path(self.project, "characters/mira.png")

    def test_private_cast_capitalization_preserves_public_story(self):
        package = package_fixture()
        package["production"]["characters"][0]["name"] = "mira"
        package["production"]["characters"][1]["name"] = "PIP"
        before = copy.deepcopy(package)
        book = story.validate_package(package, 3, 3)
        self.assertEqual(package, before)
        self.assertEqual([c["name"] for c in book["characters"]], ["Mira", "Pip", "Fern"])
        self.assertEqual(book["pages"][0]["character_ids"], ["mira"])
        for change in (lambda p: p["production"]["characters"][1].update(name="Someone Else"),
                       lambda p: p["production"]["characters"][1].update(name="MIRA"),
                       lambda p: p["story"]["metadata"]["characters"].append("mira")):
            bad = copy.deepcopy(package)
            change(bad)
            with self.assertRaises(ValueError):
                story.validate_package(bad, 3, 4)

    def test_full_length_books_expand_all_pages(self):
        for count in (12, 24):
            package = package_fixture()
            first_pages = package["story"]["pages"]
            package["story"]["pages"] = [dict(copy.deepcopy(first_pages[i % 3]), pageNumber=i + 1)
                                          for i in range(count)]
            project = copy.deepcopy(self.project)
            project.update(package)
            project["book"] = story.validate_package(package, count, 3)
            expanded = render.expand_assets(project, {"scene"})["expand"]
            saves = [n["inputs"]["spec"] for n in expanded.values() if n["class_type"] == "BookV2SaveAsset"]
            self.assertEqual([s["name"] for s in saves],
                             ["cover.png"] + [f"pages/page-{i:03d}.png" for i in range(1, count + 1)])
            self.assertEqual(saves[-1]["references"], ["style.png"])

    def test_expansion_orders_every_asset_and_uses_image_latents(self):
        expanded = render.expand_assets(self.project, {"style", "character"})["expand"]
        saves = [(nid, n) for nid, n in expanded.items() if n["class_type"] == "BookV2SaveAsset"]
        self.assertEqual([n["inputs"]["spec"]["name"] for _, n in saves],
                         ["style.png", "characters/mira.png", "characters/pip.png", "characters/fern.png"])
        prompts = [n for n in expanded.values() if n["class_type"] == "BookV2Prompt"]
        self.assertEqual(prompts[0]["inputs"]["after"], "")
        for i in range(1, len(prompts)):
            self.assertEqual(prompts[i]["inputs"]["after"], [saves[i - 1][0], 0])
        samplers = [n for n in expanded.values() if n["class_type"] == "KSampler"]
        for n in samplers[1:]:
            self.assertEqual(expanded[n["inputs"]["latent_image"][0]]["class_type"], "VAEEncode")

    def test_resumable_assets_and_complete_export(self):
        import numpy as np
        import torch
        from PIL import Image
        rng = np.random.default_rng(12)
        image = torch.from_numpy(rng.random((1, 1024, 1024, 3), dtype=np.float32))
        specs = story.asset_specs(self.project)
        for spec in specs:
            storage.save_asset(self.project, spec, image)
            self.assertTrue(storage.valid_asset(self.project, spec))
        self.assertEqual(render.expand_assets(self.project, {"style", "character"})["expand"], {})
        sheet, summary, root = export.export_book(self.project, True)
        root = Path(root)
        self.assertEqual(json.loads((root / "manifest.json").read_text())["status"], "complete")
        self.assertEqual(json.loads((root / "book.json").read_text()), self.project["story"])
        self.assertTrue((root / "book.pdf").read_bytes().startswith(b"%PDF"))
        self.assertTrue((root / "pages/page-003.txt").exists())
        self.assertIn("Mira", (root / "IMPORT-TO-ONEMOREBOOK.md").read_text())
        export.export_book(self.project, True)  # repeat export is safe
        with Image.open(root / "layout/page-003.png") as laid_out:
            self.assertEqual(laid_out.size, (1120, 1536))
        bad = dict(specs[0], signature="wrong")
        with self.assertRaises(ValueError):
            storage.valid_asset(self.project, bad)

    def test_partial_resume_renders_only_missing_page(self):
        import numpy as np
        import torch
        image = torch.from_numpy(np.random.default_rng(42).random((1, 1024, 1024, 3), dtype=np.float32))
        for spec in story.asset_specs(self.project):
            if spec["name"] != "pages/page-002.png":
                storage.save_asset(self.project, spec, image)
        self.assertEqual(render.expand_assets(self.project, {"style", "character"})["expand"], {})
        expanded = render.expand_assets(self.project, {"scene"})["expand"]
        saves = [n["inputs"]["spec"]["name"] for n in expanded.values() if n["class_type"] == "BookV2SaveAsset"]
        self.assertEqual(saves, ["pages/page-002.png"])
        self.assertEqual(len([n for n in expanded.values() if n["class_type"] == "KSampler"]), 1)
        with self.assertRaisesRegex(ValueError, "Book is incomplete"):
            export.export_book(self.project, False)


if __name__ == "__main__":
    unittest.main()
