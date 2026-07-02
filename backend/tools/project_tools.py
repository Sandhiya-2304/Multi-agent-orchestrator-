import os
from pathlib import Path

if os.environ.get("VERCEL"):
    OUTPUT_DIR = Path("/tmp/output").resolve()
else:
    OUTPUT_DIR = Path("output").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_project_folder(folder_name: str) -> Path:
    path = OUTPUT_DIR / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_file(folder: Path, filename: str, content: str):
    file_path = folder / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(file_path)


def write_sdlc_project(folder_name: str, data: dict):
    """
    Converts SDLC output into real files on disk
    """

    folder = create_project_folder(folder_name)

    files_written = []

    file_map = {
        "requirements.txt": data.get("requirements", ""),
        "user_stories.txt": data.get("user_stories", ""),
        "architecture.txt": data.get("architecture", ""),
        "main.py": data.get("code", ""),
        "testing.txt": data.get("testing", ""),
        "documentation.txt": data.get("documentation", ""),
        "deployment.txt": data.get("deployment", ""),
        "codereview.txt": data.get("code_review", "")
    }

    for file_name, content in file_map.items():
        path = write_file(folder, file_name, content)
        files_written.append(path)

    return {
        "folder": str(folder),
        "files": files_written
    }