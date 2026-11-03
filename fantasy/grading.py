"""Draft rank movement, weighted so early ranks matter more than bench ranks."""
import csv
import re
import hashlib
from pathlib import Path
from rapidfuzz import fuzz, process

FUZZ_THRESHOLD = 85
HAS_RAPIDFUZZ = True
SUPPORTED_SEASON = 2026
SCORING_VERSION = '2026-softer-misses-v15'
VALUE_RANK_LIMIT = 160
EARLY_PICK_LIMIT = 24
MAX_VALUE_MULTIPLIER = 3.0
MAX_LOSS_MULTIPLIER = 2.0
GAIN_BONUS_WEIGHT = 0.60
EARLY_GAIN_CAP = 30.0
LATE_GAIN_CAP = 90.0
EARLY_LOSS_CAP = 80.0
LATE_LOSS_CAP = 10.0
GRADE_BANDS = [
    (120, 'A+'),
    (105, 'A'),
    (90, 'A-'),
    (75, 'B+'),
    (60, 'B'),
    (45, 'B-'),
    (30, 'C+'),
    (15, 'C'),
    (0, 'C-'),
    (-15, 'D+'),
    (-30, 'D'),
    (-45, 'D-'),
]
RANKINGS_PATH = Path(__file__).resolve().parent / 'data' / 'rankings.csv'
RANKINGS_VERSION = '2026-sha256-' + hashlib.sha256(RANKINGS_PATH.read_bytes()).hexdigest()


def normalize_name(name: str) -> str:
    n = name.lower().replace("'", "").replace(".", "").replace("-", " ")
    n = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\s*$", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def pick_limits(pick: int):
    """Allow more late upside but less late downside, without tier-boundary jumps."""
    progress = (min(pick, VALUE_RANK_LIMIT) - 1) / (VALUE_RANK_LIMIT - 1)
    gain = EARLY_GAIN_CAP + (LATE_GAIN_CAP - EARLY_GAIN_CAP) * progress
    loss = LATE_LOSS_CAP + (EARLY_LOSS_CAP - LATE_LOSS_CAP) * (1 - progress) ** 2
    return round(gain, 1), round(loss, 1)


def score_pick(pick: int, rank: int | None):
    """Score rank movement, starter quality and the draft investment involved."""
    max_gain, max_loss = pick_limits(pick)
    if rank is None:
        return {'rankChange': None, 'scoredRankChange': None,
                'rankWeight': 0.0, 'baseValue': 0.0,
                'valueMultiplier': 0.0, 'uncappedSurplus': 0.0,
                'maxGain': max_gain, 'maxLoss': max_loss,
                'isCapped': False, 'surplus': 0.0}
    then = min(pick, VALUE_RANK_LIMIT)
    now = min(rank, VALUE_RANK_LIMIT)
    change = then - now
    weight = (1 - min(then, now) / VALUE_RANK_LIMIT) ** 2
    base = change * weight
    multiplier = 1.0
    if change > 0:
        # Landing a high-ranked starter late matters more than a bench upgrade.
        multiplier += GAIN_BONUS_WEIGHT * (min(MAX_VALUE_MULTIPLIER, then / now) - 1)
    elif change < 0:
        # Small drift stays small; large relative misses hurt early picks most.
        decline = (now - then) / then
        investment = min(1.0, EARLY_PICK_LIMIT / then) ** 2
        multiplier += min(MAX_LOSS_MULTIPLIER - 1, decline ** 3) * investment
    uncapped = round(base * multiplier, 1) or 0.0
    surplus = max(-max_loss, min(max_gain, uncapped))
    return {'rankChange': pick - rank, 'scoredRankChange': change,
            'rankWeight': round(weight, 4), 'baseValue': round(base, 1) or 0.0,
            'valueMultiplier': round(multiplier, 4),
            'uncappedSurplus': uncapped, 'maxGain': max_gain, 'maxLoss': max_loss,
            'isCapped': surplus != uncapped, 'surplus': surplus}


def grade_letter(total: float) -> str:
    """Zero total is C-; each 15 points moves one step; below -45 is F."""
    for minimum, letter in GRADE_BANDS:
        if total >= minimum:
            return letter
    return 'F'


def load_rankings(path: Path):
    text = path.read_text(encoding="utf-8").splitlines()
    reader = csv.DictReader(text)
    required = {"Rank", "Name", "Team", "Position"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(
            f"Rankings file {path} is missing columns: {sorted(missing)}. "
            f"Found: {reader.fieldnames}. Rankings could not be loaded.")
    rows = list(reader)
    rank_by_norm = {}
    pos_rank = {}
    counters = {}
    for r in rows:
        norm = normalize_name(r["Name"])
        # A shared name cannot identify one ranked player reliably.
        rank_by_norm[norm] = r if norm not in rank_by_norm else None
        pos = r["Position"]
        counters[pos] = counters.get(pos, 0) + 1
        pos_rank[norm] = f"{pos}{counters[pos]}"
    return rows, rank_by_norm, pos_rank


def match_player(draft_name, draft_pos, rank_by_norm):
    if draft_pos in ("K", "D/ST"):
        return None, "special-teams"
    norm = normalize_name(draft_name)
    if norm in rank_by_norm:
        row = rank_by_norm[norm]
        return row, "exact" if row else "ambiguous"
    if HAS_RAPIDFUZZ:
        best = process.extractOne(norm, list(rank_by_norm.keys()), scorer=fuzz.ratio)
        if best and best[1] >= FUZZ_THRESHOLD:
            row = rank_by_norm[best[0]]
            return row, f"fuzzy:{best[1]}" if row else "ambiguous"
        return None, "unranked"
    import difflib
    cands = difflib.get_close_matches(norm, rank_by_norm.keys(), n=1, cutoff=0.85)
    if cands:
        row = rank_by_norm[cands[0]]
        return row, "fuzzy:difflib" if row else "ambiguous"
    return None, "unranked"


_ROWS, _RANKS, _POSITION_RANKS = load_rankings(RANKINGS_PATH)


def evaluate(picks):
    scored, warnings = [], []
    matched_names = set()
    for pick in picks:
        number, name, pos, rnd = (pick['overallPick'], pick['playerName'],
                                  pick['position'], pick['round'])
        row, how = match_player(name, pos, _RANKS)
        rank = int(row['Rank']) if row else None
        ignored = row is None
        value = score_pick(number, rank)
        now = _POSITION_RANKS[normalize_name(row['Name'])] if row else (
            'K/DST' if how == 'special-teams' else 'unranked')
        if how != 'exact':
            warnings.append({'overallPick': number, 'code': how.split(':')[0],
                             'message': ('K/DST is not ranked; excluded from grading'
                                         if how == 'special-teams' else
                                         'Multiple ranked players share this name; excluded from grading'
                                         if how == 'ambiguous' else
                                         'No rankings match; excluded from grading'
                                         if row is None else
                                         'Fuzzy name match; verify matchedPlayerName')})
        if row:
            matched = normalize_name(row['Name'])
            if matched in matched_names:
                warnings.append({'overallPick': number, 'code': 'duplicate_match',
                                 'message': 'Multiple submitted names resolve to the same ranked player'})
            matched_names.add(matched)
            if row['Position'] != pos:
                warnings.append({'overallPick': number, 'code': 'position_mismatch',
                                 'message': 'Submitted position differs from rankings; original name-based scoring preserved'})
        scored.append({'pick': number, 'round': rnd, 'player': name, 'pos': pos,
                       'current_rank': rank, 'current_pos_rank': now, 'match': how,
                       **value,
                       'ignored': ignored,
                       'matchedPlayerName': row['Name'] if row else None,
                       'matchedPosition': row['Position'] if row else None})
    graded = [p for p in scored if not p['ignored']]
    total = round(sum(p['surplus'] for p in graded), 1) or 0.0
    average = total / len(graded) if graded else 0.0
    return {'totalSurplus': total, 'averageSurplus': average,
            'letterGrade': grade_letter(total) if graded else 'N/A', 'provisional': True,
            'gradeBasis': 'totalSurplus',
            'gradeNote': ('No picks have a rankings match; no grade is available.'
                          if not graded else None),
            'scoringVersion': SCORING_VERSION,
            'pickCount': len(scored), 'gradedPickCount': len(graded),
            'ignoredPickCount': len(scored) - len(graded), 'picks': scored,
            'bestPicks': sorted(graded, key=lambda p: p['surplus'], reverse=True)[:3],
            'worstPicks': sorted(graded, key=lambda p: p['surplus'])[:3],
            'warnings': warnings}
