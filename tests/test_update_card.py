"""Tests for UpdateCard: the neon sweep-glow border (ConfigCard pattern) while
checking for updates — masked to a thin rim (opaque inner layer), NO spinner,
button never resizes."""

from src.ui.components.settings.update_card import UpdateCard


def _make_card():
    return UpdateCard(on_check_update_click=lambda e: None)


def test_no_spinner_ring():
    """The card must NOT have a ProgressRing spinner (user rejected it)."""
    card = _make_card()
    assert not hasattr(card, "_progress_ring")


def test_font_sizes_not_shrunk():
    """Font sizes must not shrink: title 14, version 12, button label 12."""
    card = _make_card()
    # Title 'XenRay Client' — the top label the user flagged.
    title_text = card.content.controls[0].controls[0]
    assert title_text.value == "XenRay Client"
    assert title_text.size == 14
    # Version text
    assert card._version_text.size == 12
    # Button label — must NOT shrink.
    assert card._btn_text.size == 12
    # No ButtonStyle text_style override may shrink the label.
    assert getattr(card._update_btn.style, "text_style", None) is None


def test_has_sweep_gradient_disc():
    """The card carries the ConfigCard-style SweepGradient disc, idle = hidden."""
    card = _make_card()
    assert hasattr(card, "_sweep_disc")
    assert hasattr(card, "_sweep_gradient")
    assert card._sweep_disc.gradient is None


def test_disc_positioned_not_layout_participant():
    """The disc uses NEGATIVE offsets so it never sizes the Stack."""
    card = _make_card()
    assert card._sweep_disc.left < 0
    assert card._sweep_disc.top < 0


def test_opaque_inner_mask_present():
    """The opaque inner layer masks the disc center (ConfigCard pattern) —
    only the 1.5px rim shows the sweep, not the whole circle."""
    card = _make_card()
    assert card._inner_button_container.bgcolor == "#161922"
    assert card._inner_button_container.content is card._update_btn


def test_button_has_explicit_width():
    """The button wrapper has an explicit width so it never resizes."""
    card = _make_card()
    assert card._btn_wrapper.width == 180
    # The inner OutlinedButton ALSO carries an explicit width (fits inside
    # the 180 wrapper) so the label swap can never resize the button.
    assert card._update_btn.width == 170
    assert card._update_btn.width < card._btn_wrapper.width


def test_set_checking_true_starts_glow_no_resize():
    """set_checking(True): glow arms, icon stays visible, width unchanged."""
    card = _make_card()
    w_before = card._btn_wrapper.width
    btn_w_before = card._update_btn.width

    card.set_checking(True)

    assert card._update_btn.disabled is True
    assert card._btn_icon.visible is True  # icon NOT toggled -> no resize
    assert card._sweep_animating is True
    assert card._sweep_disc.gradient is card._sweep_gradient
    assert card._btn_text.value != "Check for Updates"
    assert card._btn_wrapper.width == w_before  # wrapper never resizes
    assert card._update_btn.width == btn_w_before  # inner button never resizes


def test_set_checking_false_stops_glow():
    """set_checking(False) re-enables the button and hides the glow."""
    card = _make_card()
    w_before = card._btn_wrapper.width
    btn_w_before = card._update_btn.width

    card.set_checking(True)
    card.set_checking(False)

    assert card._update_btn.disabled is False
    assert card._btn_icon.visible is True
    assert card._sweep_animating is False
    assert card._sweep_disc.gradient is None
    assert card._btn_wrapper.width == w_before
    assert card._update_btn.width == btn_w_before
