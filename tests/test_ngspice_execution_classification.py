import subprocess

from spec2testbench.infrastructure.simulator.pyspice_simulator import PySpiceSimulator


def _simulator():
    sim = object.__new__(PySpiceSimulator)
    sim.ngspice_path = "/usr/bin/ngspice"
    sim.timeout = 30.0
    return sim


def test_zero_returncode_with_explicit_ngspice_error_is_failure(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="ngspice-42 done\n",
            stderr="ERROR: AC startfreq <= 0\nError: no such vector Vin\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _simulator()._run_ngspice(tmp_path / "bad.ckt", tmp_path / "bad.raw")

    assert result["success"] is False
    assert result["returncode"] == 0
    assert result["error_type"] == "ngspice_execution_error"
    assert result["error_message"] == "ERROR: AC startfreq <= 0"


def test_warning_only_is_not_fatal(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="ngspice-42 done\n",
            stderr="Warning: harmless diagnostic\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _simulator()._run_ngspice(tmp_path / "warning.ckt", tmp_path / "warning.raw")

    assert result["success"] is True
    assert result["returncode"] == 0
    assert result["error_type"] is None


def test_nonzero_returncode_is_failure(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=2, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _simulator()._run_ngspice(tmp_path / "bad_rc.ckt", tmp_path / "bad_rc.raw")

    assert result["success"] is False
    assert result["returncode"] == 2
    assert result["error_type"] == "ngspice_execution_error"


def test_existing_fatal_indicator_is_failure(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="timestep too small; transient analysis aborted\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _simulator()._run_ngspice(tmp_path / "transient.ckt", tmp_path / "transient.raw")

    assert result["success"] is False
    assert result["error_type"] == "ngspice_execution_error"
