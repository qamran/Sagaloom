"""NC detection (R-W3): a licence text or URL that marks content non-commercial."""

import pytest

from sagaloom.licence import is_nc


@pytest.mark.parametrize(
    ("text", "url", "expected"),
    [
        ("CC BY-NC-SA 3.0", None, True),
        ("Creative Commons Attribution-NonCommercial-ShareAlike", None, True),
        (None, "https://creativecommons.org/licenses/by-nc-sa/3.0/", True),
        ("Non-commercial use only", None, True),
        (
            "Creative Commons Attribution-Share Alike 4.0",
            "https://creativecommons.org/licenses/by-sa/4.0/",
            False,
        ),
        ("CC BY-SA 4.0", None, False),
        ("SYNC licence", None, False),
        (None, None, False),
    ],
)
def test_is_nc_cases(text, url, expected):
    assert is_nc(text, url) is expected
