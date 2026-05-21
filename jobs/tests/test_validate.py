"""Deterministic tests — no LLM calls. Run on every commit.

These catch structural bugs: missing commands, broken parsing,
invalid schemas, inconsistent help text.
"""



class TestSchemaValidation:
    """Validation functions accept valid input and reject invalid input."""

    def test_valid_insight(self):
        from ingestion.validate import validate_insight
        v, e = validate_insight({"category": "lock-in-freedom", "reframe": "test"})
        assert v is not None

    def test_reject_missing_reframe(self):
        from ingestion.validate import validate_insight
        v, e = validate_insight({"category": "lock-in-freedom"})
        assert v is None

    def test_reject_invalid_category(self):
        from ingestion.validate import validate_insight
        v, e = validate_insight({"category": "made-up", "reframe": "test"})
        assert v is None

    def test_strip_unknown_fields(self):
        from ingestion.validate import validate_insight
        v, e = validate_insight({"category": "cost-reality", "reframe": "test", "refidence": "typo"})
        assert v is not None
        assert "refidence" not in v

    def test_all_six_categories_valid(self):
        from ingestion.validate import validate_insight
        for cat in ["lock-in-freedom", "regulatory-pressure", "capability-vs-dependency",
                     "cost-reality", "developer-experience", "resilience-reliability"]:
            v, _ = validate_insight({"category": cat, "reframe": "test"})
            assert v is not None, f"{cat} should be valid"

    def test_valid_change(self):
        from ingestion.validate import validate_change
        v, _ = validate_change({"statement": "You stop renting.", "context": "The shift."})
        assert v is not None

    def test_reject_change_without_statement(self):
        from ingestion.validate import validate_change
        v, _ = validate_change({"context": "No statement"})
        assert v is None

    def test_valid_worldview(self):
        from ingestion.validate import validate_worldview
        v, _ = validate_worldview({"belief": "Systems should work for you.", "pain": "Lock-in."})
        assert v is not None

    def test_persona_stringifies_objects(self):
        from ingestion.validate import validate_persona
        v, _ = validate_persona({"name": "Maria", "role": "CTO", "profile": {"goals": ["scale"]}})
        assert v is not None
        assert isinstance(v["profile"], str)


class TestAskParsing:
    """parse_ask_args correctly routes personas."""

    def test_seth(self):
        from mothertree.ask import parse_ask_args
        p, q = parse_ask_args(["seth", "what", "is", "the", "change?"])
        assert p == "seth" and "change" in q

    def test_lawrence(self):
        from mothertree.ask import parse_ask_args
        p, q = parse_ask_args(["lawrence", "how", "to", "close"])
        assert p == "lawrence"

    def test_trainer(self):
        from mothertree.ask import parse_ask_args
        p, q = parse_ask_args(["trainer"])
        assert p == "trainer"

    def test_onboarding(self):
        from mothertree.ask import parse_ask_args
        p, q = parse_ask_args(["onboarding"])
        assert p == "onboarding"

    def test_default(self):
        from mothertree.ask import parse_ask_args
        p, q = parse_ask_args(["what", "is", "our", "promise?"])
        assert p is None and "promise" in q

    def test_case_insensitive(self):
        from mothertree.ask import parse_ask_args
        p, _ = parse_ask_args(["SETH", "test"])
        assert p == "seth"


class TestBotConsistency:
    """The bot's detect phase handles all advertised commands and personas."""

    def test_detect_handles_global_commands(self):
        """All global commands are recognized by the detect phase."""
        from bot.detect import GLOBAL_COMMANDS
        for cmd in ["enroll", "status", "progress", "stats", "help"]:
            assert cmd in GLOBAL_COMMANDS, f"Command '{cmd}' not in GLOBAL_COMMANDS"

    def test_ask_personas_match_ask_module(self):
        """Personas in the ask module should include all advertised ones."""
        from mothertree.ask import PERSONAS, parse_ask_args

        for persona in ["seth", "lawrence"]:
            assert persona in PERSONAS, f"Persona '{persona}' not in PERSONAS dict"
            p, _ = parse_ask_args([persona, "test"])
            assert p == persona

        for special in ["trainer", "onboarding"]:
            p, _ = parse_ask_args([special])
            assert p == special
