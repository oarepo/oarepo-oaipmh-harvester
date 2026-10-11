# SPDX-FileCopyrightText: 2020-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""OAI-PMH harvester for OARepo / Invenio RDM repositories.

User documentation (defining harvesters, running and scheduling harvests, writer
options) is in the project README. This package documentation describes the internals.

## Architecture

* [oai_harvester][oarepo_oaipmh_harvester.oai_harvester] - registry of harvesters
  (database model, service, REST resource `/api/oai/harvest/harvesters`). A harvester
  stores the OAI-PMH endpoint and the datastream definition (loader, transformers,
  writers).
* [tasks][oarepo_oaipmh_harvester.tasks] - builds an invenio-vocabularies datastream
  (reader - transformers - writers) from a harvester and runs it as a Celery task.
* [transformers][oarepo_oaipmh_harvester.transformers] - `oai-import` transformer
  converting the harvested XML with an import registered on the target model.
* [writers][oarepo_oaipmh_harvester.writers] - `oai-service` writer synchronizing the
  local record with the harvested one ("the harvest always wins") and tracking the result.
* [oai_record][oarepo_oaipmh_harvester.oai_record] - harvest records: one row per
  harvested OAI identifier with original / transformed data, local pid and errors (service,
  REST resource `/api/oai/harvest/records`, search index).
* [jobs][oarepo_oaipmh_harvester.jobs] - per-harvester invenio-jobs job types.
* [administration][oarepo_oaipmh_harvester.administration] - invenio-administration views.
* [permissions][oarepo_oaipmh_harvester.permissions] - permission policies and generators.
* [cli][oarepo_oaipmh_harvester.cli] - `invenio oai` commands,
  [fixtures][oarepo_oaipmh_harvester.fixtures] - `oai_harvesters.yaml` fixture.

## Registration

The Flask extension
[OARepoOAIHarvesterExt][oarepo_oaipmh_harvester.ext.OARepoOAIHarvesterExt] is registered
via `invenio_base.apps` / `invenio_base.api_apps`; its services, indexers and harvester
jobs are registered in [finalize_apps][oarepo_oaipmh_harvester.ext.finalize_apps]
(`invenio_base.finalize_app` / `api_finalize_app`). Other entry points (`pyproject.toml`):
database models and alembic migrations, search mappings, API blueprints, administration
views, Celery tasks, the `run_all_harvesters` job, the `oai` CLI group and the
`oai_harvesters` fixture.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("oarepo-oai-pmh-harvester")
except PackageNotFoundError:
    __version__ = "0.0.0dev0+unknown"


__all__ = ["__version__"]
