"""Drug interaction & allergy checking — rule + KB lookup."""
from models import db, DrugInteraction, Allergy, Medicine


def _norm(s):
    return (s or '').strip().lower()


def check_member_interactions(member_id):
    """
    Check all pairs of active medicines for a member.
    Returns list of dicts: {a, b, severity, description}
    """
    meds = Medicine.query.filter_by(member_id=member_id).all()
    if len(meds) < 2:
        return []

    # Build lookup keys: name + generic
    keys = {}
    for m in meds:
        for k in {_norm(m.name), _norm(m.generic_name)}:
            if k:
                keys.setdefault(k, m)

    findings = []
    seen = set()
    drug_list = list(keys.keys())

    for i, a in enumerate(drug_list):
        for b in drug_list[i + 1:]:
            pair = tuple(sorted([a, b]))
            if pair in seen:
                continue
            seen.add(pair)

            hits = DrugInteraction.query.filter(
                ((DrugInteraction.drug_a == a) & (DrugInteraction.drug_b == b)) |
                ((DrugInteraction.drug_a == b) & (DrugInteraction.drug_b == a))
            ).all()

            for h in hits:
                findings.append({
                    'a': keys[a].name,
                    'b': keys[b].name,
                    'severity': h.severity,
                    'description': h.description,
                })

    # Sort HIGH > MODERATE > LOW
    order = {'HIGH': 0, 'MODERATE': 1, 'LOW': 2}
    findings.sort(key=lambda x: order.get(x['severity'], 3))
    return findings


def check_allergies(member_id, medicine):
    """Return list of allergy matches for a medicine."""
    allergies = Allergy.query.filter_by(member_id=member_id).all()
    hits = []
    m_keys = {_norm(medicine.name), _norm(medicine.generic_name),
              _norm(medicine.category)}
    for a in allergies:
        if _norm(a.allergen) in m_keys:
            hits.append({
                'allergen': a.allergen,
                'severity': a.severity,
                'notes': a.notes,
            })
    return hits