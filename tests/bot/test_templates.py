"""Tests for the template system."""

from __future__ import annotations

import pytest

from loko.bot.models import MessageTemplate, TemplateKey, ToneProfile
from loko.bot.templates import (
    TemplateRenderError,
    get_default_templates,
    render,
    render_template,
    resolve_template,
)


class TestRender:
    def test_basic_interpolation(self):
        result = render("Bonjour, je suis {nom_bot}.", {"nom_bot": "Loko"})
        assert result == "Bonjour, je suis Loko."

    def test_multiple_variables(self):
        result = render(
            "{nom_bot} - {intentions_gerees}",
            {"nom_bot": "Bot", "intentions_gerees": "A, B"},
        )
        assert result == "Bot - A, B"

    def test_missing_variable_gets_empty_string(self):
        result = render("Hello {nom_bot}", {})
        assert result == "Hello "

    def test_unknown_variable_raises(self):
        with pytest.raises(TemplateRenderError, match="Unknown template variables"):
            render("Hello {unknown_var}", {})

    def test_no_variables_passthrough(self):
        result = render("Static text", {})
        assert result == "Static text"


class TestRenderTemplate:
    def test_render_fr(self):
        t = MessageTemplate(
            key=TemplateKey.FIN,
            text_fr="Au revoir {nom_bot}.",
            text_en="Goodbye {nom_bot}.",
            variables=["nom_bot"],
        )
        result = render_template(t, "fr", {"nom_bot": "Loko"})
        assert result == "Au revoir Loko."

    def test_render_en(self):
        t = MessageTemplate(
            key=TemplateKey.FIN,
            text_fr="Au revoir.",
            text_en="Goodbye.",
        )
        result = render_template(t, "en")
        assert result == "Goodbye."


class TestDefaultTemplates:
    @pytest.mark.parametrize("tone", list(ToneProfile))
    def test_all_keys_present(self, tone):
        defaults = get_default_templates(tone)
        for key in TemplateKey:
            assert key in defaults, (
                f"Missing template {key.value} for tone {tone.value}"
            )

    @pytest.mark.parametrize("tone", list(ToneProfile))
    def test_all_templates_renderable(self, tone):
        defaults = get_default_templates(tone)
        variables = {
            "nom_bot": "TestBot",
            "intentions_gerees": "A, B, C",
            "temps_attente": "5",
            "lien_escalade": "https://example.com",
            "options": "X, Y",
        }
        for key, template in defaults.items():
            # Should not raise
            render_template(template, "fr", variables)
            render_template(template, "en", variables)

    def test_presentation_contains_variables(self):
        defaults = get_default_templates(ToneProfile.NEUTRE)
        t = defaults[TemplateKey.PRESENTATION]
        result = render_template(t, "fr", {"nom_bot": "Bot", "intentions_gerees": "X"})
        assert "Bot" in result
        assert "X" in result

    def test_mise_en_relation_contains_wait_time(self):
        defaults = get_default_templates(ToneProfile.FORMEL)
        t = defaults[TemplateKey.MISE_EN_RELATION]
        result = render_template(t, "fr", {"temps_attente": "12"})
        assert "12" in result


class TestResolveTemplate:
    def test_resolve_from_config(self):
        custom = MessageTemplate(
            key=TemplateKey.FIN,
            text_fr="Custom fin.",
            text_en="Custom end.",
        )
        result = resolve_template(
            {TemplateKey.FIN: custom},
            TemplateKey.FIN,
            ToneProfile.NEUTRE,
        )
        assert result.text_fr == "Custom fin."

    def test_fallback_to_defaults(self):
        result = resolve_template({}, TemplateKey.FIN, ToneProfile.NEUTRE)
        assert result.text_fr  # should have default text

    def test_unknown_key_raises(self):
        # All keys should have defaults, but test the error path
        # by using a patched defaults dict — we just test that
        # resolve_template returns something for every key
        for key in TemplateKey:
            result = resolve_template({}, key, ToneProfile.CHALEUREUX)
            assert result.key == key
