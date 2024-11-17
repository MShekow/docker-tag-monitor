# Docker Tag Monitor

Docker Tag Monitor is a web service that tells you how often a Docker/OCI image has changed over time (assuming that it has been monitoring the image/tag for a while).

You can use hosted version https://docker-tag-monitor.augmentedmind.de/ or host it yourself with Docker compose or Kubernetes.

## Background

Registries such as Docker Hub do _not_ store or expose how often a specific image/tag has changed. Given a specific tag, you can merely look up the _age_ of the most recent push. But a small number, e.g. "1 day", is _not_ a good indicator for the update frequency of an image. The maintainers might update an image tag only twice a _year_, and coincidentally the last updated happened to be 1 day ago.

However, the rebuild frequency of image version tags _should_ be one of your evaluation criteria when choosing (base) images, so that's why _Docker Tag Monitor_ was created.

See this blog post (TODO) for more details.

## Used components

- The frontend and backend is implemented in Python using [Reflex](https://reflex.dev/). The used template is [predix](https://github.com/jeremiahdanielregalario/predix) (see also [here](https://predix.reflex.run/)). Reflex allows to implement the frontend in Python, compiling the frontend to React components, and establishing a permanently-running websocket between frontend and backend.
- The scraper that regularly fetches image digest updates is also written in Python
- The database uses PostgreSQL

## Self-hosting / configuration

There is a **Docker compose** (see `compose.yml`) stack, or a **Kubernetes Helm chart** (in the `charts/docker-tag-monitor` folder).

There are various **configuration options** you can tune via environment variables. Just search the code base for `os.getenv(...)` ([GitHub search](https://github.com/search?q=repo%3AMShekow%2Fdocker-tag-monitor%20os.getenv%28&type=code)), where the variables are also documented. 

## Package management with Poetry

### Setup

On a new machine, create a venv for Poetry (in path `<project-root>/.poetry`), and one for the project itself (in path `<project-root>/.venv`), e.g. via `C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe -m venv <path>`.
This separation is necessary to avoid dependency _conflicts_ between the project and Poetry.

Using the `pip` of the Poetry venv, install Poetry via `pip install -r requirements-poetry.txt`

Then, run `poetry install`, but make sure that either no venv is active, or the `.venv` one, but **not** the `.poetry` one (otherwise Poetry would stupidly install the dependencies into that one).

### Usage

- When dependencies changed **from the outside**, e.g. because Renovate updated the `pyproject.toml` and `poetry.lock` file, run `poetry install --sync` to update the local environment, where `--sync` removes any obsolete dependencies from the `.venv` venv.
- If **you** updated a dependency in `pyproject.toml`, run `poetry update` to update the lock file and the local environment.
- To only update the **transitive** dependencies (keeping the ones in `pyproject.toml` the same), run `poetry update --sync`, which updates the lock file and also installs the updates into the active venv.

Make sure the `.venv` venv is active while running any of the above `poetry` commands.
