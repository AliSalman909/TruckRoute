from api.services.ranking import explain_recommendation, find_safe_departure, rank_routes, score_route
from api.services.risk import RiskLevel as R
from api.services.spatial import METERS_PER_MILE

MI = METERS_PER_MILE


def make(route_id, levels, duration_h=10, seg_mi=25):
    return score_route(route_id, duration_h * 3600, [(lvl, seg_mi * MI) for lvl in levels])


def ids(scores):
    return [s.route_id for s in rank_routes(scores)]


def test_score_counts_miles_and_average():
    s = make("r", [R.LOW, R.HIGH, R.SEVERE, R.LOW])
    assert s.counts[R.HIGH] == 1
    assert round(s.miles[R.SEVERE]) == 25
    assert s.avg_risk == (0 + 2 + 3 + 0) / 4
    assert s.max_level == R.SEVERE
    assert s.is_viable


def test_no_travel_makes_route_non_viable_and_last():
    bad = make("bad", [R.NO_TRAVEL] + [R.LOW] * 9, duration_h=5)
    good = make("good", [R.SEVERE] * 3 + [R.LOW] * 7, duration_h=15)
    assert not bad.is_viable
    assert ids([bad, good]) == ["good", "bad"]


def test_priority_order_severe_then_high_then_avg_then_time():
    fewer_severe = make("a", [R.SEVERE] + [R.HIGH] * 5, duration_h=20)
    more_severe = make("b", [R.SEVERE] * 2, duration_h=8)
    assert ids([more_severe, fewer_severe]) == ["a", "b"]

    fewer_high = make("c", [R.HIGH] + [R.MODERATE] * 5, duration_h=20)
    more_high = make("d", [R.HIGH] * 2, duration_h=8)
    assert ids([more_high, fewer_high]) == ["c", "d"]

    calmer = make("e", [R.LOW] * 4, duration_h=12)
    windier = make("f", [R.MODERATE] * 4, duration_h=9)
    assert ids([windier, calmer]) == ["e", "f"]

    fast = make("g", [R.LOW] * 4, duration_h=9)
    slow = make("h", [R.LOW] * 4, duration_h=12)
    assert ids([slow, fast]) == ["g", "h"]


def test_severe_is_compared_in_miles_not_checkpoint_count():
    # One Severe checkpoint covering 50 mi vs two covering 10 mi each.
    long_seg = score_route("long", 3600, [(R.SEVERE, 50 * MI)])
    short_segs = score_route("short", 7200, [(R.SEVERE, 10 * MI), (R.SEVERE, 10 * MI)])
    assert ids([long_seg, short_segs]) == ["short", "long"]


def test_explanation_names_deciding_criterion():
    a = make("a", [R.LOW] * 4, duration_h=9)
    b = make("b", [R.SEVERE] + [R.LOW] * 3, duration_h=8)
    assert "Severe" in explain_recommendation(rank_routes([a, b]))


def test_find_safe_departure_returns_first_viable_shift():
    def evaluate(shift):
        level = R.NO_TRAVEL if shift < 6 else R.LOW
        return [make("r1", [level]), make("r2", [R.NO_TRAVEL])]

    shift, best = find_safe_departure(evaluate, max_shift_h=24)
    assert shift == 6
    assert best.route_id == "r1"


def test_find_safe_departure_none_when_always_unsafe():
    assert find_safe_departure(lambda h: [make("r", [R.NO_TRAVEL])], max_shift_h=24) is None
