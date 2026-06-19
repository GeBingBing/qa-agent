from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "Agently.create_dynamic_task" in text
    assert "TaskDAG.from_yaml" in text
    assert "TaskDAGValidator" in text
    assert "TaskDAGExecutor" in text


if __name__ == "__main__":
    main()
