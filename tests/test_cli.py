from typer.testing import CliRunner

from deepgram_transcribe.cli import app, route_args

runner = CliRunner()


def test_help_lists_commands():
    out = runner.invoke(app, ["--help"]).output
    assert "run" in out and "render" in out


def test_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0 and "deepgram-transcribe" in res.output


def test_bare_routes_to_run():
    assert route_args(["a.m4a"]) == ["run", "a.m4a"]
    assert route_args(["--config", "c", "a.m4a"]) == ["run", "--config", "c", "a.m4a"]
    assert route_args(["render", "a.json"]) == ["render", "a.json"]
    assert route_args(["--help"]) == ["--help"]
    assert route_args([]) == []


def test_short_help_alias():
    for args in (["-h"], ["run", "-h"], ["render", "-h"]):
        res = runner.invoke(app, args)
        assert res.exit_code == 0 and "Usage" in res.output
    assert route_args(["-h"]) == ["-h"]
