"""Plain-text presentation of draft grades with aligned tables and prominent grade display."""


def format_reports(reports):
    """Format either one saved report or the collection returned by GET."""
    if isinstance(reports, list):
        return '\n\n---\n\n'.join(draft_report(r) for r in reports) if reports else 'No draft reports saved.'
    return draft_report(reports)


def _format_value(val, places=1):
    if val > 0:
        return f"+{val:.{places}f}"
    elif val < 0:
        return f"{val:.{places}f}"
    return f"{0:.{places}f}"


def _format_then_now(pick):
    if pick.get('ignored'):
        return 'Not graded'
    then = f"#{pick['pick']}"
    now = f"#{pick['current_rank']}" if pick.get('current_rank') else (pick.get('current_pos_rank') or 'Unranked')
    return f"{then} vs {now}"


def draft_report(resource):
    evaluation = resource['evaluation']
    grade_letter = evaluation['letterGrade']
    total_val = _format_value(evaluation['totalSurplus'])
    avg_val = _format_value(evaluation['averageSurplus'], places=3)

    box_inner = 80
    pad = (box_inner - 42) // 2
    inner_border = '+' + '=' * 40 + '+'
    inner_empty = '|' + ' ' * 40 + '|'
    grade_text = f"DRAFT GRADE: [ {grade_letter} ]"
    inner_grade = '|' + f"{grade_text:^40}" + '|'
    stat_text = f"Total Value: {total_val} pts    Average Value: {avg_val} pts"

    header_title = 'FANTASY DRAFT REPORT CARD'
    winners_title = 'BIGGEST WINNERS'
    losers_title = 'BIGGEST LOSERS'
    board_title = 'FULL DRAFT BOARD'

    lines = [
        "=" * 84,
        f"{header_title:^84}",
        f"Team: {resource['teamName']} | Season: {resource['season']}",
        "=" * 84,
        "",
        "+-" + "-" * box_inner + "-+",
        "| " + " " * box_inner + " |",
        "| " + " " * pad + inner_border + " " * pad + " |",
        "| " + " " * pad + inner_empty + " " * pad + " |",
        "| " + " " * pad + inner_grade + " " * pad + " |",
        "| " + " " * pad + inner_empty + " " * pad + " |",
        "| " + " " * pad + inner_border + " " * pad + " |",
        "| " + " " * box_inner + " |",
        "| " + f"{stat_text:^{box_inner}}" + " |",
        "| " + " " * box_inner + " |",
        "+-" + "-" * box_inner + "-+",
        "",
        "=" * 84,
        f"{winners_title:^84}",
        "=" * 84,
        " Rank  Player Name                 Round   Pick   Rank (Then vs Now)          Value ",
        "-" * 84,
    ]

    for i, p in enumerate(evaluation.get('bestPicks', []), 1):
        r_str = f"Rnd {p['round']}"
        pk_str = f"#{p['pick']}"
        tn_str = _format_then_now(p)
        v_str = _format_value(p['surplus'])
        lines.append(
            f"  {i}.   {p['player']:<26} {r_str:<7} {pk_str:<6} {tn_str:^24}  {v_str:>7}"
        )

    lines.extend([
        "-" * 84,
        "",
        "=" * 84,
        f"{losers_title:^84}",
        "=" * 84,
        " Rank  Player Name                 Round   Pick   Rank (Then vs Now)          Value ",
        "-" * 84,
    ])

    for i, p in enumerate(evaluation.get('worstPicks', []), 1):
        r_str = f"Rnd {p['round']}"
        pk_str = f"#{p['pick']}"
        tn_str = _format_then_now(p)
        v_str = _format_value(p['surplus'])
        lines.append(
            f"  {i}.   {p['player']:<26} {r_str:<7} {pk_str:<6} {tn_str:^24}  {v_str:>7}"
        )

    lines.extend([
        "-" * 84,
        "",
        "=" * 84,
        f"{board_title:^84}",
        "=" * 84,
        "  Rnd   Pick   Player Name                 Rank (Then vs Now)                 Value ",
        "-" * 84,
    ])

    sorted_picks = sorted(evaluation.get('picks', []), key=lambda x: x['pick'])
    for p in sorted_picks:
        pk_str = f"#{p['pick']}"
        tn_str = _format_then_now(p)
        v_str = _format_value(p['surplus'])
        lines.append(
            f" {p['round']:>4}   {pk_str:>5}   {p['player']:<27} {tn_str:^26}      {v_str:>7}"
        )

    lines.append("=" * 84)
    if evaluation.get('gradeNote'):
        lines.append(evaluation['gradeNote'])

    return "\n".join(lines)
