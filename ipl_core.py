"""
Core logic for the IPL winner predictor (no Streamlit code here, so it can be tested separately).
"""
from math import erfc, sqrt
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE = Path(__file__).parent
DATA_FILE = BASE / "data" / "matches_clean.csv"
# Also support the original ZIP layout, where the CSV sits beside this file.
if not DATA_FILE.exists():
    DATA_FILE = BASE / "matches_clean.csv"
MODEL_FILE = BASE / "ipl_model.joblib"

CAT_COLS = ["team1", "team2", "venue", "toss_decision"]
NUM_COLS = ["form_diff"]
FEATURE_COLS = CAT_COLS + NUM_COLS
BEST_C = 0.03   # chosen with time-series cross-validation in the notebook (train data only)


# ---------- data ----------
def add_form(df: pd.DataFrame) -> pd.DataFrame:
    """Each team's win rate over its previous 5 matches (the current match is excluded)."""
    df = df.sort_values(["season", "id"]).reset_index(drop=True).copy()
    rows = []
    for _, r in df.iterrows():
        rows.append({"team": r["team1"], "won": int(r["winner"] == r["team1"])})
        rows.append({"team": r["team2"], "won": int(r["winner"] == r["team2"])})
    long = pd.DataFrame(rows)
    long["form"] = long.groupby("team")["won"].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    df["form_team1"] = long.iloc[0::2]["form"].values
    df["form_team2"] = long.iloc[1::2]["form"].values
    df[["form_team1", "form_team2"]] = df[["form_team1", "form_team2"]].fillna(0.5)
    df["form_diff"] = df["form_team1"] - df["form_team2"]
    return df


def load_history() -> pd.DataFrame:
    return add_form(pd.read_csv(DATA_FILE))


# ---------- model ----------
def build_pipeline(model=None) -> Pipeline:
    prep = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
        ("num", StandardScaler(), NUM_COLS),
    ])
    return Pipeline([("prep", prep), ("model", model or LogisticRegression(max_iter=1000, C=BEST_C))])


def train_and_save(df: pd.DataFrame) -> Pipeline:
    model = build_pipeline().fit(df[FEATURE_COLS], df["team1_won"])
    joblib.dump({"model": model, "sklearn_version": sklearn.__version__}, MODEL_FILE)
    return model


def load_model(df: pd.DataFrame) -> Pipeline:
    """Load the saved model. If the file is missing, broken, or was saved with another
    scikit-learn version, retrain from the data (takes under a second)."""
    try:
        saved = joblib.load(MODEL_FILE)
        if saved.get("sklearn_version") == sklearn.__version__:
            return saved["model"]
    except Exception:
        pass
    try:
        return train_and_save(df)
    except OSError:  # read-only file system on some hosts
        return build_pipeline().fit(df[FEATURE_COLS], df["team1_won"])


# ---------- prediction ----------
def recent_form(team: str, history: pd.DataFrame, n: int = 5) -> float:
    games = history[(history["team1"] == team) | (history["team2"] == team)].tail(n)
    return 0.5 if games.empty else float((games["winner"] == team).mean())


def resolve_teams(team_a: str, team_b: str, toss_winner: str, decision: str):
    """In this dataset team1 is the side batting first. Work it out from the toss."""
    toss_loser = team_b if toss_winner == team_a else team_a
    if decision == "bat":
        return toss_winner, toss_loser      # (batting first, chasing)
    return toss_loser, toss_winner


def check_input(m: dict, history: pd.DataFrame) -> list:
    warns = []
    for col in CAT_COLS:
        if m.get(col) in (None, ""):
            warns.append(f"MISSING: {col}")
        elif m[col] not in set(history[col].unique()):
            warns.append(f"UNKNOWN {col}: {m[col]!r} was not in the training data and will be ignored by the model")
    if m.get("team1") == m.get("team2"):
        warns.append("team1 and team2 are the same team")
    return warns


def predict_match(model, history: pd.DataFrame, team1: str, team2: str, venue: str, decision: str) -> dict:
    """team1 = batting first, team2 = chasing."""
    m = {"team1": team1, "team2": team2, "venue": venue, "toss_decision": decision}
    warns = check_input(m, history)
    if any(w.startswith("MISSING") or "same team" in w for w in warns):
        return {"error": warns}
    f1, f2 = recent_form(team1, history), recent_form(team2, history)
    row = pd.DataFrame([{**m, "form_diff": f1 - f2}])
    p1 = float(model.predict_proba(row[FEATURE_COLS])[0, 1])
    return {"p_team1": p1, "p_team2": 1 - p1, "form_team1": f1, "form_team2": f2, "warnings": warns}


# ---------- statistics shown in the app ----------
def z_test_proportion(successes: int, n: int, p0: float = 0.5):
    p_hat = successes / n
    z = (p_hat - p0) / sqrt(p0 * (1 - p0) / n)
    p_value = erfc(abs(z) / sqrt(2))
    half = 1.96 * sqrt(p_hat * (1 - p_hat) / n)
    return {"rate": p_hat, "z": z, "p_value": p_value, "ci": (p_hat - half, p_hat + half), "n": n}


def expanding_window_accuracy(df: pd.DataFrame, first=2012, last=2019) -> pd.DataFrame:
    """Per season: learn only from earlier seasons, test on that season. Baseline = majority class."""
    rows = []
    for s in range(first, last + 1):
        tr, te = df["season"] < s, df["season"] == s
        model = build_pipeline().fit(df.loc[tr, FEATURE_COLS], df.loc[tr, "team1_won"])
        base = DummyClassifier(strategy="prior").fit(df.loc[tr, FEATURE_COLS], df.loc[tr, "team1_won"])
        y = df.loc[te, "team1_won"]
        rows.append({"season": s, "matches": int(te.sum()),
                     "model": float((model.predict(df.loc[te, FEATURE_COLS]) == y).mean()),
                     "baseline": float((base.predict(df.loc[te, FEATURE_COLS]) == y).mean())})
    return pd.DataFrame(rows).set_index("season")
