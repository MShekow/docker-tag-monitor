ToDos:
- Implement graphs for status page
- Clean up compose file (crawler vs. scraper), rename volume
- Add Renovate
- Check GitHub Dependabot alerts
- Add license
- Write Readme and blog post
- Implement missing backend features
- Add DockerHub credentials to Helm chart

## Package management

### Setup

On a new machine, create a venv for Poetry (in path `<project-root>/.poetry`), and one for the project itself (in path `<project-root>/.venv`), e.g. via `C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe -m venv <path>`.
This separation is necessary to avoid dependency _conflicts_ between the project and Poetry.

Using the `pip` of the Poetry venv, install Poetry via `pip install -r requirements.txt`

Then, run `poetry install`, but make sure that either no venv is active, or the `.venv` one, but **not** the `.poetry` one (otherwise Poetry would stupidly install the dependencies into that one).

### Usage

- When dependencies changed **from the outside**, e.g. because Renovate updated the `pyproject.toml` or `poetry.lock` file, run `poetry install --sync` to update the local environment, where `--sync` removes any obsolete dependencies from the `.venv` venv.
- If **you** updated a dependency in `pyproject.toml`, run `poetry update` to update the lock file and the local environment.
- To only update the **transitive** dependencies (keeping the ones in `pyproject.toml` the same), run `poetry update --sync`, which updates the lock file and also installs the updates into the active venv.

Make sure the `.venv` venv is active while running any of the above `poetry` commands.
