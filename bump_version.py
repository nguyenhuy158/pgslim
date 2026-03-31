import re
import sys
import argparse
from pathlib import Path


def bump_version(part):
    path = Path("pyproject.toml")
    content = path.read_text()

    # Match version = "X.Y.Z"
    match = re.search(r'version = "(\d+)\.(\d+)\.(\d+)"', content)
    if not match:
        print("Could not find version in pyproject.toml")
        sys.exit(1)

    major, minor, patch = map(int, match.groups())

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    else:
        print(f"Invalid part: {part}")
        sys.exit(1)

    new_version = f"{major}.{minor}.{patch}"
    new_content = re.sub(
        r'version = "\d+\.\d+\.\d+"', f'version = "{new_version}"', content
    )
    path.write_text(new_content)
    print(f"Bumped version to {new_version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "part", choices=["major", "minor", "patch"], default="patch", nargs="?"
    )
    args = parser.parse_args()
    bump_version(args.part)
