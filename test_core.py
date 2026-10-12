import ipl_core as core

history = core.load_history()
model = core.load_model(history)


def test_resolve_teams():
    assert core.resolve_teams("A", "B", "A", "bat") == ("A", "B")
    assert core.resolve_teams("A", "B", "A", "field") == ("B", "A")
    assert core.resolve_teams("A", "B", "B", "bat") == ("B", "A")


def test_normal_prediction_is_a_probability():
    r = core.predict_match(model, history, "Chennai Super Kings", "Mumbai Indians",
                           "MA Chidambaram Stadium, Chepauk", "bat")
    assert 0 <= r["p_team1"] <= 1 and abs(r["p_team1"] + r["p_team2"] - 1) < 1e-9
    assert r["warnings"] == []


def test_unknown_venue_warns_but_does_not_crash():
    r = core.predict_match(model, history, "Chennai Super Kings", "Mumbai Indians", "New Stadium", "field")
    assert "p_team1" in r and any("UNKNOWN venue" in w for w in r["warnings"])


def test_bad_input_gives_error():
    assert "error" in core.predict_match(model, history, "Mumbai Indians", "Mumbai Indians", "Wankhede Stadium", "bat")
    assert "error" in core.predict_match(model, history, "Mumbai Indians", "Chennai Super Kings", "Wankhede Stadium", "")


def test_form_has_no_leakage_first_match_is_neutral():
    first = history.iloc[0]
    assert first["form_team1"] == 0.5 and first["form_team2"] == 0.5


def test_z_test_matches_notebook():
    n = len(history)
    chase = core.z_test_proportion(int((history["team1_won"] == 0).sum()), n)
    assert round(chase["rate"], 3) == 0.555 and chase["p_value"] < 0.01


def test_no_missing_values():
    assert history.isnull().sum().sum() == 0
