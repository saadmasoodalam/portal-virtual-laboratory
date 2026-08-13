from pvl.experiments.matrix import build_rig_v1_dc_baseline_states, randomized_repeated_dc_matrix


def test_baseline_state_ids_are_complete():
    states = build_rig_v1_dc_baseline_states()
    assert {state.state_id for state in states} == {
        "off_off", "a_positive", "a_negative", "b_positive", "b_negative",
        "both_same_positive", "both_same_negative", "both_opposed_ab", "both_opposed_ba",
    }


def test_randomized_matrix_is_reproducible():
    first = randomized_repeated_dc_matrix(repetitions=3, seed=42)
    second = randomized_repeated_dc_matrix(repetitions=3, seed=42)
    assert first == second
    assert len(first) == 27


def test_each_block_starts_with_off_control():
    runs = randomized_repeated_dc_matrix(repetitions=3, seed=42)
    for repetition in range(1, 4):
        block = [run for run in runs if run.repetition_index == repetition]
        assert block[0].state_id == "off_off"
        assert len({run.state_id for run in block}) == 9


def test_opposed_dc_state_uses_coil_polarity_not_frequency_sign():
    states = {state.state_id: state for state in build_rig_v1_dc_baseline_states()}
    state = states["both_opposed_ab"]
    assert (state.coil_a.polarity, state.coil_b.polarity) == (1, -1)
    assert (state.coil_a.omega_sign, state.coil_b.omega_sign) == (1, 1)
