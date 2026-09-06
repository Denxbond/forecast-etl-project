"""Run isolated dbt with the project's local connection settings."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    project = PROJECT_ROOT / 'dbt' / 'weather_dbt'
    executable = PROJECT_ROOT / '.venv-dbt' / 'bin' / 'dbt'
    if not executable.is_file():
        print('Install dbt first: make install-dbt', file=sys.stderr)
        return 1
    values = {**dotenv_values(PROJECT_ROOT / '.env', interpolate=False), **os.environ}
    required = ('WAREHOUSE_HOST', 'WAREHOUSE_PORT', 'WAREHOUSE_USER',
                'WAREHOUSE_PASSWORD', 'WAREHOUSE_DATABASE')
    missing = [name for name in required if not values.get(name)]
    if missing:
        print(f"Missing settings: {', '.join(missing)}", file=sys.stderr)
        return 1
    env = {key: value for key, value in values.items() if value is not None}
    env['DBT_ENV_SECRET_WAREHOUSE_PASSWORD'] = env.pop('WAREHOUSE_PASSWORD')
    env['DBT_SEND_ANONYMOUS_USAGE_STATS'] = 'false'
    profile = project / 'profiles.yml'
    if not profile.exists():
        shutil.copyfile(project / 'profiles.example.yml', profile)
    return subprocess.run(
        [str(executable), *sys.argv[1:], '--project-dir', str(project),
         '--profiles-dir', str(project)], cwd=project, env=env,
    ).returncode


if __name__ == '__main__':
    raise SystemExit(main())
