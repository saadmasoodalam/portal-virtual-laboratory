from pvl.solvers.getdp.poc001_run import ConvergencePoint, evaluate_poc001_gate


def _point(h: float, nodes: int, elements: int, field_scale: float = 1.0) -> ConvergencePoint:
    field = tuple(field_scale * value for value in (1.0, 2.0, 3.0, 2.0, 1.0))
    return ConvergencePoint(
        characteristic_length_m=h,
        metrics={
            "max_relative_error": 0.005,
            "mean_relative_error": 0.0025,
            "rms_relative_error": 0.003,
            "symmetry_max_relative_difference": 2.0e-6,
        },
        b_axis_t=field,
        node_count=nodes,
        element_count=elements,
    )


def test_poc001_gate_accepts_stable_accurate_refinement_sequence():
    points = [
        _point(0.03, 7000, 14000, 1.0005),
        _point(0.02, 12000, 24000, 1.0001),
        _point(0.012, 28000, 56000, 1.0),
    ]
    gate = evaluate_poc001_gate(points)
    assert gate.passed
    assert all(gate.criteria.values())


def test_poc001_gate_rejects_large_pointwise_error():
    points = [
        _point(0.03, 7000, 14000, 1.0005),
        _point(0.02, 12000, 24000, 1.0001),
        _point(0.012, 28000, 56000, 1.0),
    ]
    bad = points[-1]
    points[-1] = ConvergencePoint(
        characteristic_length_m=bad.characteristic_length_m,
        metrics={**bad.metrics, "max_relative_error": 0.02},
        b_axis_t=bad.b_axis_t,
        node_count=bad.node_count,
        element_count=bad.element_count,
    )
    gate = evaluate_poc001_gate(points)
    assert not gate.passed
    assert not gate.criteria["finest_pointwise_error_within_tolerance"]
    assert not gate.criteria["all_meshes_pointwise_error_within_tolerance"]


def test_poc001_gate_rejects_nonconverged_final_field():
    points = [
        _point(0.03, 7000, 14000, 1.0),
        _point(0.02, 12000, 24000, 1.0),
        _point(0.012, 28000, 56000, 1.01),
    ]
    gate = evaluate_poc001_gate(points)
    assert not gate.passed
    assert not gate.criteria["final_successive_field_change_within_tolerance"]
