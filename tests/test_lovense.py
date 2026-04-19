"""Tests for lovense utility functions."""

from kink_mcp.lovense import lovense_model


def test_lovense_model_lvs_prefix():
    assert lovense_model("LVS-Domi") == "Domi"


def test_lovense_model_love_prefix():
    assert lovense_model("LOVE-Lush3") == "Lush3"


def test_lovense_model_no_prefix():
    assert lovense_model("Unknown") == "Unknown"


def test_lovense_model_empty_after_prefix():
    assert lovense_model("LVS-") == ""


def test_lovense_model_empty_string():
    assert lovense_model("") == ""
