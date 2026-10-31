from paladin_fixture.boundaries import clamp_count


def test_negative():
    assert clamp_count(-7) == 0


def test_zero():
    assert clamp_count(0) == 0


def test_positive():
    assert clamp_count(11) == 11
