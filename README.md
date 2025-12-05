# OARepo OAI-PMH Harvester

End-to-end OAI-PMH harvesting utilities for Invenio-based repositories: manage harvesters, launch Celery-powered imports, persist harvested records, and expose REST and administration views.

## Overview

This package extends Invenio with:

- CRUD and REST APIs for registering OAI-PMH harvesters, including facets and administration panels
- A configurable DataStream pipeline (readers → transformers → writers) for harvesting
  and importing remote records into local services
- Persistent tracking of harvested records, captured errors, and original XML payloads
- Celery tasks and Invenio Jobs integration for scheduled or ad-hoc harvesting runs
- Permission policies for repository administrators and delegated harvest managers

## Installation

```bash
pip install oarepo-oaipmh-harvester
```

Optional extras:

- `pip install oarepo-oaipmh-harvester[oarepo14]` for an Invenio RDM 14 test environment
- `pip install oarepo-oaipmh-harvester[tests]` to obtain pytest helpers used in the test-suite

### Requirements

- Python 3.13 or 3.14
- Invenio 14.x with a compatible OpenSearch/Elasticsearch backend
- `invenio-oaipmh-scythe` for OAI-PMH client functionality
- `invenio-jobs` for scheduled harvesting
- A running Celery worker when executing background harvest tasks

## Key Features

### 1. Harvester Registry & REST Services

**Source:** [`oarepo_oaipmh_harvester/oai_harvester/service.py`](oarepo_oaipmh_harvester/oai_harvester/service.py), [`oarepo_oaipmh_harvester/oai_harvester/api.py`](oarepo_oaipmh_harvester/oai_harvester/api.py), [`oarepo_oaipmh_harvester/oai_harvester/views.py`](oarepo_oaipmh_harvester/oai_harvester/views.py)

- `OAIHarvesterService` provides CRUD, search, and `harvest` actions with pagination, suggestion, and rich facet definitions (`facets.py`).
- Aggregated records expose model-backed properties (`OAIHarvesterAggregate`) while `HarvesterDumper` stores metadata to OpenSearch.
- REST blueprints are registered automatically, and tests in [`tests/test_harvester_crud.py`](tests/test_harvester_crud.py) validate end-to-end creation, indexing, updates, and deletion.

```python
from invenio_access.permissions import system_identity
from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service

current_oai_harvester_service.create(system_identity, {
    "id": "zenodo",
    "name": "Zenodo OAI",
    "base_url": "https://zenodo.org/oai2d",
    "metadata_prefix": "oai_dc",
    "loader": "oai-pmh",
    "transformers": ['oai-import{model:"rdmrecord"}'],
    "writers": ['oai-service{model:"rdmrecord",update:true}']
})
```

### 2. Configurable Harvest Pipeline

**Source:** [`oarepo_oaipmh_harvester/tasks.py`](oarepo_oaipmh_harvester/tasks.py), [`oarepo_oaipmh_harvester/transformers/oai_import.py`](oarepo_oaipmh_harvester/transformers/oai_import.py), [`oarepo_oaipmh_harvester/writers/oai_service.py`](oarepo_oaipmh_harvester/writers/oai_service.py), [`oarepo_oaipmh_harvester/config.py`](oarepo_oaipmh_harvester/config.py)

- `harvest_oaipmh_records` builds a DataStream pipeline from string-based loader/transformer/writer definitions using JSON5 arguments.
- `OAIImportTransformer` resolves the proper model import based on the harvested XML namespace and local name.
- `OAIServiceWriter` writes into the target OARepo model service, deduplicates on datestamp, handles deletions, and stores status information.
- `VOCABULARIES_DATASTREAM_TRANSFORMERS` and `_WRITERS` register these components globally at extension init time.
- Sample pipeline execution is exercised in [`tests/test_harvest_task.py`](tests/test_harvest_task.py), which mocks remote responses and asserts that harvested records land both in the target model and the tracking index.

### 3. Harvested Record Tracking & Search

**Source:** [`oarepo_oaipmh_harvester/oai_record/api.py`](oarepo_oaipmh_harvester/oai_record/api.py), [`oarepo_oaipmh_harvester/oai_record/models.py`](oarepo_oaipmh_harvester/oai_record/models.py), [`oarepo_oaipmh_harvester/oai_record/service.py`](oarepo_oaipmh_harvester/oai_record/service.py), [`oarepo_oaipmh_harvester/oai_record/dumpers.py`](oarepo_oaipmh_harvester/oai_record/dumpers.py)

- `OAIHarvestedRecord` persists original XML, transformed payloads, error lists, and links back to the originating harvester.
- The service exposes facets over error codes, deletion flags, and harvester assignments, with `AddHarvesterDumperExt` injecting harvester context into search documents.
- Relationship fields (`harvester_id`, `harvester`) provide ORM-level joins, fixed in the SQLAlchemy model by declaring the foreign-key column explicitly.
- Permission policies (`OAIRecordPermissionPolicy`) allow administrators and harvest managers to inspect logs while keeping data restricted.

### 4. Celery Tasks & Invenio Jobs Integration

**Source:** [`oarepo_oaipmh_harvester/tasks.py`](oarepo_oaipmh_harvester/tasks.py), [`oarepo_oaipmh_harvester/jobs.py`](oarepo_oaipmh_harvester/jobs.py)

- Harvest executions run through a Celery task (`harvest_oaipmh_records`) and stream results synchronously or asynchronously.
- `register_oaipmh_job` creates dynamic `JobType` subclasses per harvester, enabling individual scheduling through `invenio-jobs`.
- `finalize_apps` re-registers jobs on startup so scheduled runs survive restarts.

### 5. Administration & Proxies

**Source:** [`oarepo_oaipmh_harvester/proxies.py`](oarepo_oaipmh_harvester/proxies.py), [`oarepo_oaipmh_harvester/administration/harvester/views.py`](oarepo_oaipmh_harvester/administration/harvester/views.py), [`oarepo_oaipmh_harvester/administration/record/views.py`](oarepo_oaipmh_harvester/administration/record/views.py)

- Flask proxies expose `current_oai_harvester_service` and `current_oai_record_service` for reuse in CLI tasks, tests, and application extensions.
- Administration entry points register list, detail, create, and edit screens for both harvesters and harvested records inside `invenio-administration`.

### 6. Permissions & Access Control

**Source:** [`oarepo_oaipmh_harvester/permissions.py`](oarepo_oaipmh_harvester/permissions.py)

- Custom generators (`AdministrationWithQueryFilter`, `HarvestManager`, `HarvestRecordManager`) combine action-based permissions with per-harvester manager lists.
- `harvest_action` can be granted to roles or users to allow API-triggered harvest runs without full administration rights.
- Search filters ensure that users only see harvesters and records they manage.

### 7. REST Mappings & Search Configuration

**Source:** [`oarepo_oaipmh_harvester/oai_harvester/mappings`](oarepo_oaipmh_harvester/oai_harvester/mappings), [`oarepo_oaipmh_harvester/oai_record/mappings`](oarepo_oaipmh_harvester/oai_record/mappings)

- OpenSearch mappings are shipped with the package and loaded through entry points, ensuring consistent indexing for harvester registries and harvested records.
- `OAIRecordSearchOptions` and `OAIHarvesterSearchOptions` configure suggestion parsers, pagination defaults, and facet sets tailored to OAI workflows.

## Development

### Setup

```bash
git clone https://github.com/oarepo/oarepo-oaipmh-harvester.git
cd oarepo-oaipmh-harvester

./run.sh venv
```

The helper script downloads the shared OARepo runner, prepares a virtual environment, and installs development requirements.

### Running Tests

```bash
./run.sh test
# or directly
pytest
```

Key tests:

- [`tests/test_harvester_crud.py`](tests/test_harvester_crud.py) – validates CRUD, search, and indexing operations for harvesters.
- [`tests/test_harvest_task.py`](tests/test_harvest_task.py) – mocks an entire harvest pipeline, processes Celery queue outputs, and asserts on stored records and tracking entries.

## Entry Points

```ini
[project.entry-points]
"invenio_base.apps" =
	oarepo_oaipmh = oarepo_oaipmh_harvester.ext:OARepoOAIHarvesterExt
"invenio_base.api_apps" =
	oarepo_oaipmh = oarepo_oaipmh_harvester.ext:OARepoOAIHarvesterExt
"invenio_base.api_blueprints" =
	oarepo-oaipmh-harvester = oarepo_oaipmh_harvester.oai_harvester.views:create_api_blueprint
	oarepo-oaipmh-harvester_record = oarepo_oaipmh_harvester.oai_record.views:create_api_blueprint
"invenio_base.finalize_app" =
	oarepo_oaipmh_harvester = oarepo_oaipmh_harvester.ext:finalize_apps
"invenio_base.api_finalize_app" =
	oarepo_oaipmh_harvester = oarepo_oaipmh_harvester.ext:finalize_apps
"invenio_celery.tasks" =
	oarepo_harvest = oarepo_oaipmh_harvester.tasks
"invenio_jobs.jobs" =
	harvest_oaipmh_records = oarepo_oaipmh_harvester.jobs:OAIHarvestJob
"invenio_db.models" =
	oarepo-oaipmh-harvester = oarepo_oaipmh_harvester.oai_harvester.models
	oarepo-oaipmh-harvester-record = oarepo_oaipmh_harvester.oai_record.models
"invenio_db.alembic" =
	oarepo_oaipmh_harvester = oarepo_oaipmh_harvester:alembic
"invenio_administration.views" =
	oarepo_oai_harvester_list = oarepo_oaipmh_harvester.administration.harvester.views:OAIPMHListView
	oarepo_oaipmh_create = oarepo_oaipmh_harvester.administration.harvester.views:OAIPMHCreateView
	oarepo_oaipmh_harvester_edit = oarepo_oaipmh_harvester.administration.harvester.views:OAIPMHEditView
	oarepo_oaipmh_harvester_details = oarepo_oaipmh_harvester.administration.harvester.views:OAIPMHDetailView
	oarepo_oaipmh_record_list = oarepo_oaipmh_harvester.administration.record.views:RecordListView
	oarepo_oaipmh_record_details = oarepo_oaipmh_harvester.administration.record.views:RecordDetailView
"invenio_access.actions" =
	harvest_action = oarepo_oaipmh_harvester.permissions:harvest_action
"invenio_search.mappings" =
	oai-harvester = oarepo_oaipmh_harvester.oai_harvester.mappings
	oai-harvest-record = oarepo_oaipmh_harvester.oai_record.mappings
```

## License

Copyright (c) 2025 CESNET z.s.p.o.

Released under the MIT License. See [LICENSE](LICENSE) for details.

## Links

- Documentation & Source: <https://github.com/oarepo/oarepo-oaipmh-harvester>
- Issues: <https://github.com/oarepo/oarepo-oaipmh-harvester/issues>
- OARepo Project: <https://github.com/oarepo>

## Acknowledgments

This project builds upon the [Invenio](https://inveniosoftware.org/) framework and is developed as part of the OARepo ecosystem for FAIR-ready repositories.

