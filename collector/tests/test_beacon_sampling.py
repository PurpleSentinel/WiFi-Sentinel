import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope='module')
def sampler(tmp_path_factory):
    compiler = shutil.which('cc')
    if not compiler:
        pytest.skip('Host C compiler required for firmware sampling regression checks')
    root = Path(__file__).resolve().parents[2]
    binary = tmp_path_factory.mktemp('beacon-sampler') / 'sampler'
    subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I', str(root / 'firmware/main'), str(root / 'firmware/tests/beacon_sampler.c'),
                    '-o', str(binary)], check=True, capture_output=True)
    def run(*args):
        return json.loads(subprocess.check_output([str(binary), *map(str, args)]))
    return run


def test_four_periodic_aps_are_not_starved(sampler):
    old = [0, 0, 0, 0]
    for i in range(4000):
        if (i + 1) % 20 == 0:
            old[i % 4] += 1
    assert old == [0, 0, 0, 200]  # Original global-counter blind spot.
    assert sampler('periodic', 4, 1000, 20) == [50, 50, 50, 50]


@pytest.mark.parametrize('aps,factor', [(1, 1), (4, 2), (20, 20), (40, 20), (64, 1000)])
def test_each_stable_ap_gets_first_and_one_per_n_observations(sampler, aps, factor):
    rounds = 1001
    assert sampler('periodic', aps, rounds, factor) == [(rounds + factor - 1) // factor] * aps


@pytest.mark.parametrize('scenario', ['subtypes', 'settings', 'unsampled'])
def test_independent_types_channels_runtime_changes_and_unsampled_frames(sampler, scenario):
    assert sampler(scenario) is True


def test_fixed_state_survives_unique_address_churn_and_reports_returning_aps(sampler):
    state = sampler('eviction')
    assert state['capacity'] == 64
    assert state['bytes'] < 2048
