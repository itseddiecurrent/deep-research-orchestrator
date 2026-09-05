from research_agent import __version__
from research_agent.cli import main


def test_cli_without_query_prints_help(capsys: object) -> None:
    assert main([]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "usage: research-agent" in captured.out


def test_cli_version(capsys: object) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert f"research-agent {__version__}" in captured.out


def test_cli_discloses_unimplemented_live_adapters(capsys: object) -> None:
    assert main(["Research an unseen topic"]) == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Live CLI research is not available yet" in captured.err
    assert "provider adapters" in captured.err
