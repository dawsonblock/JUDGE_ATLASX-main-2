from app.services.classifier import classify_event


def test_event_classifier_maps_detention_order():
    result = classify_event("The court entered an order of detention pending trial.")
    assert result.event_type == "detention_order"
    assert result.confidence >= 0.9
    assert "order of detention" in result.matched_keywords


def test_repeat_offender_indicators_are_explicit():
    result = classify_event("The filing references criminal history category IV and danger to the community.")
    assert result.repeat_offender_indicator is True
    assert "criminal history category" in result.repeat_offender_indicators
    assert "danger to the community" in result.repeat_offender_indicators
