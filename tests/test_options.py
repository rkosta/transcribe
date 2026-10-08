import pytest

from deepgram_transcribe.options import _truthy, build_params


@pytest.mark.parametrize(
    "v", ["false", "FALSE", " False ", "0", "no", "No", "off", " OFF", "", None, False]
)
def test_truthy_off(v):
    assert _truthy(v) is False


@pytest.mark.parametrize("v", ["true", "1", "yes", "on", True])
def test_truthy_on(v):
    assert _truthy(v) is True


@pytest.mark.parametrize("v", ["0", "no", "off"])
def test_detect_language_off_values_keep_english_features(v):
    params, dropped = build_params({"language": "en", "topics": True}, {}, {"detect_language": [v]})
    assert dropped == [] and "topics" in params
