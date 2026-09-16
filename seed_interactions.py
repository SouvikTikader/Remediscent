"""Populate drug interaction knowledge base with common interactions."""
from models import db, DrugInteraction

# Curated sample — extend as needed
INTERACTIONS = [
    # (drug_a, drug_b, severity, description)
    ('warfarin', 'aspirin', 'HIGH',
     'Increased bleeding risk. Avoid combination unless supervised.'),
    ('warfarin', 'ibuprofen', 'HIGH',
     'Significantly increased bleeding risk. Use acetaminophen instead.'),
    ('aspirin', 'ibuprofen', 'MODERATE',
     'Ibuprofen may reduce aspirin cardioprotective effect.'),
    ('metformin', 'alcohol', 'MODERATE',
     'Risk of lactic acidosis. Limit alcohol intake.'),
    ('atorvastatin', 'clarithromycin', 'HIGH',
     'Increased risk of muscle damage (rhabdomyolysis).'),
    ('simvastatin', 'amlodipine', 'MODERATE',
     'Limit simvastatin dose to 20 mg/day.'),
    ('lisinopril', 'potassium', 'HIGH',
     'Risk of hyperkalemia. Monitor potassium levels.'),
    ('metoprolol', 'verapamil', 'HIGH',
     'Risk of bradycardia and heart block.'),
    ('sertraline', 'tramadol', 'HIGH',
     'Risk of serotonin syndrome and seizures.'),
    ('ciprofloxacin', 'antacid', 'MODERATE',
     'Antacids reduce ciprofloxacin absorption. Separate by 2 hours.'),
    ('paracetamol', 'warfarin', 'MODERATE',
     'Regular high-dose paracetamol may increase INR.'),
    ('omeprazole', 'clopidogrel', 'MODERATE',
     'Omeprazole reduces clopidogrel activation.'),
    ('metformin', 'prednisone', 'LOW',
     'Corticosteroids may raise blood glucose; monitor.'),
    ('amlodipine', 'simvastatin', 'MODERATE',
     'Increase risk of muscle toxicity.'),
    ('diclofenac', 'aspirin', 'HIGH',
     'Increased GI bleeding risk.'),
]


def seed_interactions():
    if DrugInteraction.query.count() > 0:
        print('Interactions already seeded.')
        return
    for a, b, sev, desc in INTERACTIONS:
        db.session.add(DrugInteraction(
            drug_a=a.lower(), drug_b=b.lower(),
            severity=sev, description=desc))
    db.session.commit()
    print(f' Seeded {len(INTERACTIONS)} interactions.')