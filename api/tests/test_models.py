import pytest
from pydantic import ValidationError

from sagaloom.models import Entry


def test_entry_version_must_be_positive():
    with pytest.raises(ValidationError):
        Entry(id="ent_0001", world_id="w", title="T", type="place", body="", version=0)
