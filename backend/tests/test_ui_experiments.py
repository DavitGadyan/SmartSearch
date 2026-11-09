"""UI experiments: config defaults, assumed-effect multipliers in the click model, hypothesis verdicts, fallback drafting."""

import numpy as np

from app.schemas.experiments import UiConfig
from app.services.experiment_draft_service import YES, hypothesis_verdict, slug


def test_ui_config_defaults_match_the_current_storefront() -> None:
    c = UiConfig()
    assert c.cta_label == "Add to cart" and c.cta_style == "dark" and c.show_ratings and c.card_badges
    assert UiConfig(cta_style="accent", cta_label="Add to bag").model_dump()["cta_label"] == "Add to bag"


def test_effects_scale_the_funnel_probabilities(monkeypatch) -> None:
    """With a +100% add-to-cart effect, carts (given clicks) roughly double on the same random draws."""
    from app.simulation import click_model as cm

    class Cache:
        in_stock = np.ones(50)
        price_z = np.zeros(50)
        style = np.array([""] * 50)
        brand = np.array([""] * 50)
        product_class = np.array([""] * 50)

    class User:
        patience = 50
        style: dict = {}
        brands: dict = {}
        classes: dict = {}
        log_price_offset = 0.0

    pos = np.arange(50)
    grades = np.full(50, 2)
    carts = []
    for eff in (None, {"add_to_cart_rate": 1.0}):
        rng = np.random.default_rng(3)
        _, carted, _ = cm.simulate_interactions(User(), pos, grades, Cache(), rng, eff)
        carts.append(int(carted.sum()))
    assert carts[1] > carts[0]


def test_hypothesis_verdict_language() -> None:
    assert hypothesis_verdict({"p_value": 0.01, "control": 0.10, "treatment": 0.12}).startswith("Reject H0")
    assert hypothesis_verdict({"p_value": 0.40, "control": 0.10, "treatment": 0.12}).startswith(
        "Fail to reject H0"
    )


def test_slug_and_yes_detection() -> None:
    s = slug("Green Add-to-bag button!")
    assert s.startswith("green_add_to_bag_button_") and len(s.split("_")[-1]) == 6
    assert YES.search("Yes, launch it") and not YES.search("make the button green")
