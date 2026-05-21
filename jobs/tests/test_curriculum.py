"""Tests for training curriculum — role-specific paths."""
import pytest


class TestCurriculumLookup:
    """Look up stages, chapters, and trainers by role."""

    def test_hunter_has_5_stages(self):
        from training.curriculum import get_stages
        assert len(get_stages("hunter")) == 5

    def test_gatherer_has_5_stages(self):
        from training.curriculum import get_stages
        assert len(get_stages("gatherer")) == 5

    def test_farmer_has_5_stages(self):
        from training.curriculum import get_stages
        assert len(get_stages("farmer")) == 5

    def test_citizen_has_4_stages(self):
        from training.curriculum import get_stages
        assert len(get_stages("citizen")) == 4

    def test_hunter_stage0_has_3_chapters(self):
        from training.curriculum import get_chapters
        assert len(get_chapters("hunter", 0)) == 3

    def test_gatherer_stage0_has_2_chapters(self):
        from training.curriculum import get_chapters
        assert len(get_chapters("gatherer", 0)) == 2

    def test_farmer_stage0_has_2_chapters(self):
        from training.curriculum import get_chapters
        assert len(get_chapters("farmer", 0)) == 2

    def test_citizen_stage0_has_chapters(self):
        from training.curriculum import get_chapters
        assert len(get_chapters("citizen", 0)) >= 1

    def test_get_chapter_returns_trainer(self):
        from training.curriculum import get_chapter
        ch = get_chapter("hunter", 0, 0)
        assert ch["trainer"] == "saga"
        assert ch["name"] == "The Promise"
        assert "change" in ch["tables"]

    def test_hunter_stage1_is_offering(self):
        from training.curriculum import get_chapter
        ch = get_chapter("hunter", 1, 0)
        assert ch["trainer"] == "saga"
        assert ch["name"] == "The Services"

    def test_hunter_stage2_is_lena(self):
        from training.curriculum import get_chapter
        ch = get_chapter("hunter", 2, 0)
        assert ch["trainer"] == "lena"
        assert ch["name"] == "The Consultative Conversation"

    def test_hunter_stage3_is_mixed(self):
        from training.curriculum import get_chapter
        assert get_chapter("hunter", 3, 0)["trainer"] == "saga"
        assert get_chapter("hunter", 3, 1)["trainer"] == "lena"

    def test_hunter_stage4_is_the_hunt(self):
        from training.curriculum import get_chapter
        ch = get_chapter("hunter", 4, 0)
        assert ch["trainer"] == "lena"
        assert ch["name"] == "Signal Recognition"

    def test_get_chapter_gatherer_stage1(self):
        from training.curriculum import get_chapter
        ch = get_chapter("gatherer", 1, 0)
        assert ch["trainer"] == "lena"

    def test_get_chapter_farmer_stage1(self):
        from training.curriculum import get_chapter
        ch = get_chapter("farmer", 1, 0)
        assert ch["trainer"] == "lena"

    def test_get_total_chapters(self):
        from training.curriculum import get_total_chapters
        assert get_total_chapters("hunter", 0) == 3
        assert get_total_chapters("gatherer", 0) == 2

    def test_unknown_role_raises(self):
        from training.curriculum import get_stages
        with pytest.raises(KeyError):
            get_stages("nonexistent")

    def test_is_citizen(self):
        from training.curriculum import is_citizen_role
        assert is_citizen_role("citizen") is True
        assert is_citizen_role("hunter") is False
