from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path
import pandas as pd
import ipl_core as core

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(ROOT / 'static'), static_url_path='/static')

try:
    HISTORY = core.load_history()
    MODEL = core.load_model(HISTORY)
    INIT_ERROR = None
except Exception as exc:
    HISTORY, MODEL, INIT_ERROR = pd.DataFrame(), None, str(exc)


def ready():
    if INIT_ERROR or HISTORY.empty or MODEL is None:
        return False
    return True

@app.get('/')
def index():
    return send_from_directory(ROOT / 'static', 'index.html')

@app.get('/api/health')
def health():
    return jsonify({'status': 'ok' if ready() else 'error', 'matches': len(HISTORY), 'error': INIT_ERROR})

@app.get('/api/meta')
def meta():
    if not ready():
        return jsonify({'error': INIT_ERROR or 'Model could not be loaded'}), 500
    return jsonify({
        'teams': sorted(set(HISTORY.team1.dropna()) | set(HISTORY.team2.dropna())),
        'venues': sorted(HISTORY.venue.dropna().unique().tolist()),
        'matches': int(len(HISTORY)),
        'seasons': [int(x) for x in sorted(HISTORY.season.dropna().unique())],
        'latest_season': int(HISTORY.season.max())
    })

@app.post('/api/predict')
def predict():
    if not ready():
        return jsonify({'error': INIT_ERROR or 'Model could not be loaded'}), 500
    data = request.get_json(silent=True) or {}
    team_a, team_b = data.get('team_a'), data.get('team_b')
    toss_winner, decision, venue = data.get('toss_winner'), data.get('decision'), data.get('venue')
    if not all([team_a, team_b, toss_winner, decision, venue]):
        return jsonify({'error': 'Please complete every field.'}), 400
    if team_a == team_b:
        return jsonify({'error': 'Choose two different teams.'}), 400
    if toss_winner not in (team_a, team_b):
        return jsonify({'error': 'Toss winner must be one of the selected teams.'}), 400
    if decision not in ('bat', 'field'):
        return jsonify({'error': 'Toss decision must be bat or field.'}), 400
    first, chase = core.resolve_teams(team_a, team_b, toss_winner, decision)
    result = core.predict_match(MODEL, HISTORY, first, chase, venue, decision)
    if 'error' in result:
        return jsonify({'error': '; '.join(result['error'])}), 400
    return jsonify({
        'batting_first': first, 'chasing': chase,
        'p_first': round(float(result['p_team1']), 6),
        'p_chase': round(float(result['p_team2']), 6),
        'form_first': round(float(result['form_team1']), 4),
        'form_chase': round(float(result['form_team2']), 4),
        'warnings': result['warnings'],
        'note': 'Historical model estimate only — not a guarantee or betting advice.'
    })

@app.get('/api/insights')
def insights():
    if not ready():
        return jsonify({'error': INIT_ERROR or 'Model could not be loaded'}), 500
    h = HISTORY
    n = len(h)
    chase_wins = int((h.team1_won == 0).sum())
    toss_wins = int((h.toss_winner == h.winner).sum())
    chase = core.z_test_proportion(chase_wins, n)
    toss = core.z_test_proportion(toss_wins, n)
    played = pd.concat([h[['team1']].rename(columns={'team1':'team'}), h[['team2']].rename(columns={'team2':'team'})])
    matches = played.groupby('team').size()
    wins = h.winner.value_counts()
    table = pd.DataFrame({'team': matches.index, 'matches': matches.values})
    table['wins'] = table.team.map(wins).fillna(0).astype(int)
    table['win_rate'] = (table.wins / table.matches).round(4)
    table = table.sort_values('win_rate', ascending=False)
    seasons = h.groupby('season').team1_won.apply(lambda s: round(float((1-s.mean())*100), 2))
    return jsonify({
        'matches': n, 'chase_rate': round(chase['rate'], 4), 'chase_ci': [round(x,4) for x in chase['ci']], 'chase_p': round(chase['p_value'],6),
        'toss_rate': round(toss['rate'],4), 'toss_ci': [round(x,4) for x in toss['ci']], 'toss_p': round(toss['p_value'],6),
        'teams': table.to_dict(orient='records'), 'chase_by_season': [{'season':int(k),'rate':v} for k,v in seasons.items()]
    })

@app.get('/api/report')
def report():
    if not ready():
        return jsonify({'error': INIT_ERROR or 'Model could not be loaded'}), 500
    try:
        val = core.expanding_window_accuracy(HISTORY)
        total = int(val.matches.sum())
        model_acc = float((val.model * val.matches).sum() / total)
        baseline_acc = float((val.baseline * val.matches).sum() / total)
        rows = [{'season':int(idx),'matches':int(r.matches),'model':round(float(r.model),4),'baseline':round(float(r.baseline),4)} for idx,r in val.iterrows()]
        return jsonify({'seasons':rows,'model_accuracy':round(model_acc,4),'baseline_accuracy':round(baseline_acc,4),'test_matches':total})
    except Exception as exc:
        return jsonify({'error': f'Could not generate validation report: {exc}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
