from market_radar_ai.market_data.capture import connectivity_exit_code

def test_empty_valid_series_is_not_connectivity_failure():
    assert connectivity_exit_code({'captures':[{'payload':{'provider_status':'ok','candles':[],'quality_passed_at_capture':False}},{'payload':{'provider_status':'ok','candles':[{}]}}]})==0

def test_provider_error_still_fails():
    assert connectivity_exit_code({'captures':[{'payload':{'provider_status':'error','candles':[]}}]})==1
