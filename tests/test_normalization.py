from app.services.normalization import Normalizer


def test_normalizes_charge_currency_and_payment_term():
    normalizer = Normalizer()
    assert normalizer.charge_name("H/D Fee") == "Handling Charge"
    assert normalizer.currency("rmb") == "CNY"
    assert normalizer.payment_term("collect") == "CC"
