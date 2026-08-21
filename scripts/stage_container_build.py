"""Stage the serving-only requirements for an isolated container build."""

# 0) Imports
from __future__ import annotations
import re
import shutil
import tomllib
from pathlib import Path


# 1) Sub functions
def dependency_name(requirement: str) -> str:
    name = re.split(r"[\s<>=!~@\[]", requirement, maxsplit=1)[0]
    return name.lower().replace("_", "-")


def project_dependencies(pyproject_path: Path) -> list[str]:
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    runtime_dependencies = [
        dependency
        for dependency in dependencies
        if dependency_name(dependency) != "pyarrow"
    ]
    return runtime_dependencies


def stage_container_build(project_root: Path) -> Path:
    runtime_dependencies = project_dependencies(project_root / "pyproject.toml")
    staging_dir = project_root / ".docker"
    # The ignored directory is one generated staging snapshot, not a user workspace.
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir()
    requirements_path = staging_dir / "runtime-requirements.txt"
    requirements_path.write_text(
        "\n".join(runtime_dependencies) + "\n",
        encoding="utf-8",
    )
    print(f"Staged {len(runtime_dependencies)} serving dependencies")
    return requirements_path


# 2) Command line
def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    stage_container_build(project_root)


if __name__ == "__main__":
    main()
