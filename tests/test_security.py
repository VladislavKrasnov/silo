from __future__ import annotations

import pytest

from app.ingest.github import GitHubCloneError, parse_repository_url, validate_git_reference
from app.security.crypto import SecretCipher, SecretDecryptionError
from app.security.environment_parser import MAX_ENVIRONMENT_VALUE_LENGTH, parse_environment_assignments
from app.security.redaction import REDACTION_PLACEHOLDER, SecretRedactor


class TestSecretCipher:
    def test_round_trips_a_value(self, cipher: SecretCipher) -> None:
        payload = cipher.encrypt("s3cret", "project-secret:1:BOT_TOKEN")
        assert cipher.decrypt(payload, "project-secret:1:BOT_TOKEN") == "s3cret"

    def test_ciphertext_is_not_reused_across_calls(self, cipher: SecretCipher) -> None:
        assert cipher.encrypt("value", "context") != cipher.encrypt("value", "context")

    def test_rejects_a_ciphertext_bound_to_another_context(self, cipher: SecretCipher) -> None:
        payload = cipher.encrypt("s3cret", "project-secret:1:BOT_TOKEN")
        with pytest.raises(SecretDecryptionError):
            cipher.decrypt(payload, "project-secret:2:BOT_TOKEN")

    def test_rejects_tampered_ciphertext(self, cipher: SecretCipher) -> None:
        payload = bytearray(cipher.encrypt("s3cret", "context"))
        payload[-1] ^= 0xFF
        with pytest.raises(SecretDecryptionError):
            cipher.decrypt(bytes(payload), "context")

    def test_rejects_truncated_ciphertext(self, cipher: SecretCipher) -> None:
        with pytest.raises(SecretDecryptionError):
            cipher.decrypt(b"short", "context")

    def test_rejects_a_key_of_the_wrong_length(self) -> None:
        with pytest.raises(ValueError):
            SecretCipher(b"too-short")


class TestEnvironmentParser:
    def test_parses_plain_assignments(self) -> None:
        parsed = parse_environment_assignments("BOT_TOKEN=abc\nLOG_LEVEL=debug\n")
        assert parsed.entries == {"BOT_TOKEN": "abc", "LOG_LEVEL": "debug"}

    def test_strips_export_prefix_and_quotes(self) -> None:
        parsed = parse_environment_assignments('export BOT_TOKEN="abc"\n')
        assert parsed.entries == {"BOT_TOKEN": "abc"}

    def test_ignores_comments_and_blank_lines(self) -> None:
        parsed = parse_environment_assignments("# comment\n\nBOT_TOKEN=abc\n")
        assert parsed.entries == {"BOT_TOKEN": "abc"}

    def test_rejects_lowercase_and_malformed_keys(self) -> None:
        parsed = parse_environment_assignments("lower=1\n9BAD=1\nNO_SEPARATOR\nGOOD=1\n")
        assert parsed.entries == {"GOOD": "1"}
        assert len(parsed.rejected_lines) == 3

    def test_rejects_control_characters_in_values(self) -> None:
        parsed = parse_environment_assignments("BOT_TOKEN=abc\x07def\n")
        assert parsed.entries == {}

    def test_rejects_oversized_values(self) -> None:
        parsed = parse_environment_assignments(f"BOT_TOKEN={'x' * (MAX_ENVIRONMENT_VALUE_LENGTH + 1)}\n")
        assert parsed.entries == {}

    def test_last_assignment_wins(self) -> None:
        parsed = parse_environment_assignments("BOT_TOKEN=first\nBOT_TOKEN=second\n")
        assert parsed.entries == {"BOT_TOKEN": "second"}


class TestSecretRedactor:
    def test_masks_known_values(self) -> None:
        redactor = SecretRedactor(["super-secret-token"])
        assert redactor.apply("auth: super-secret-token") == f"auth: {REDACTION_PLACEHOLDER}"

    def test_ignores_short_values(self) -> None:
        redactor = SecretRedactor(["ab"])
        assert redactor.apply("value ab") == "value ab"

    def test_prefers_the_longest_overlapping_value(self) -> None:
        redactor = SecretRedactor(["token-abc", "token-abc-extended"])
        assert redactor.apply("token-abc-extended") == REDACTION_PLACEHOLDER

    def test_treats_values_as_literals_not_patterns(self) -> None:
        redactor = SecretRedactor(["a.*b.token"])
        assert redactor.apply("axxbytoken") == "axxbytoken"

    def test_passes_text_through_without_secrets(self) -> None:
        assert SecretRedactor().apply("nothing to hide") == "nothing to hide"


class TestRepositoryUrlValidation:
    @pytest.mark.parametrize(
        "raw_url",
        [
            "http://github.com/owner/repository",
            "git@github.com:owner/repository.git",
            "https://user:token@github.com/owner/repository",
            "https://gitlab.com/owner/repository",
            "https://github.com/owner",
            "https://github.com/owner/repository?x=1",
            "https://github.com:8443/owner/repository",
            "https://github.com/../../etc/passwd",
            "file:///etc/passwd",
        ],
    )
    def test_rejects_unsafe_urls(self, raw_url: str) -> None:
        with pytest.raises(GitHubCloneError):
            parse_repository_url(raw_url)

    def test_normalizes_accepted_urls(self) -> None:
        coordinates = parse_repository_url("https://github.com/owner/repository")
        assert coordinates.normalized_url == "https://github.com/owner/repository.git"
        assert coordinates.repository == "repository"

    def test_accepts_a_trailing_git_suffix(self) -> None:
        assert parse_repository_url("https://github.com/owner/repo.git").repository == "repo"

    @pytest.mark.parametrize("reference", ["--upload-pack=evil", "..", "refs/heads/x.lock", "with space", ""])
    def test_rejects_unsafe_git_references(self, reference: str) -> None:
        with pytest.raises(GitHubCloneError):
            validate_git_reference(reference)

    @pytest.mark.parametrize("reference", ["main", "v1.2.3", "release/2024-01"])
    def test_accepts_conventional_git_references(self, reference: str) -> None:
        assert validate_git_reference(reference) == reference
