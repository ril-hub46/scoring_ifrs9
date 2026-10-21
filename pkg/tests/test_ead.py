import pandas as pd
import pytest

from src.ifrs9.ead import ead_at_origination, principal_from_installment


def test_principal_matches_standard_annuity():
    # 10 000 € à 12 % sur 36 mois -> mensualité de 332,14 €
    assert principal_from_installment(332.1431, 12.0, 36) == pytest.approx(10_000, abs=0.01)


def test_principal_with_zero_rate_is_installment_times_months():
    assert principal_from_installment(100.0, 0.0, 36) == pytest.approx(3_600)


def test_ead_at_origination_uses_term_in_months():
    loans = pd.DataFrame(
        {"installment": [332.1431, 222.4445], "int_rate": [12.0, 12.0], "term": [" 36 months", " 60 months"]},
        index=[7, 8],
    )

    ead = ead_at_origination(loans)

    assert ead.index.tolist() == [7, 8]
    assert ead.tolist() == pytest.approx([10_000, 10_000], abs=0.01)
