from pvl.core.poc005_models import POC005Config
from pvl.solvers.getdp.poc005 import render_magnetoquasistatic_pro


def test_poc005_sampling_plane_is_inside_insert_and_not_at_center():
    config = POC005Config()
    text = render_magnetoquasistatic_pro(config)
    sample_z = config.insert.center_z_m + 0.25 * config.insert.axial_thickness_m
    assert config.insert.center_z_m < sample_z < (
        config.insert.center_z_m + config.insert.axial_thickness_m / 2.0
    )
    assert f"{sample_z:.17g}" in text
    assert "quarter-thickness" in text
