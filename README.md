# OARepo OAI-PMH Harvester

Harvest records from remote OAI-PMH repositories into your OARepo / Invenio RDM
repository and keep them in sync.

- Register harvesters (OAI-PMH endpoint + target model) from the command line, a
  fixture file or the administration UI.
- Run harvests on demand or on a schedule (invenio-jobs); scheduled runs are
  incremental.
- Every harvested record is tracked: its original XML, the transformed data, the
  local record it was written to, and any errors - browsable in the administration UI.
- **The harvest always wins.** Whatever happened to a harvested record locally (edited,
  deleted, restored), the next harvest brings it back to the state reported by the
  source.

## Installation

```bash
pip install oarepo-oai-pmh-harvester
invenio alembic upgrade        # creates / migrates the harvester tables
invenio index init             # or create the oai-harvester and oai-harvest-record indices
```

Requirements:

- Python 3.14, OARepo 14 (Invenio RDM 14)
- a Celery worker - harvests run as Celery tasks
- the target model must be an OARepo model (`oarepo-model`) with an OAI import (see below)

## Preparing your model

The harvester converts the harvested XML with an *import* registered on the target
model. The import's `oai_name` (namespace, root element name) selects it for the
metadata format being harvested:

```python
from oarepo_model.customizations import AddMetadataImport

AddMetadataImport(
    code="datacite-xml",
    name="DataCite XML",
    mimetype="application/vnd.datacite.datacite+xml",
    deserializer=DataCiteXMLDeserializer(),
    oai_name=("http://datacite.org/schema/kernel-4", "resource"),
)
```

The deserializer gets the metadata XML element (`deserialize_xml`, if it has that
method) or its string form (`deserialize`) and returns the record data as accepted by
the model's service.

If the record's persistent identifier comes from the harvested data (the pid provider
has a `get_pid_value_from_record` class method), a record a user deposited earlier with
the same identifier is taken over and overwritten by the harvest - no duplicate is
created.

## Defining harvesters

A harvester has:

| Field | Meaning |
|---|---|
| `id` | short identifier, used on the command line and in job names |
| `name`, `comment` | human readable description |
| `base_url` | OAI-PMH endpoint |
| `metadata_prefix` | metadata format to harvest, e.g. `oai_dc`, `oai_datacite` |
| `setspec` | optional OAI-PMH set |
| `loader` | reader of the source, default `oai-pmh` |
| `transformers` | list of transformers, usually `oai-import{model:"<model>"}` |
| `writers` | list of writers, usually `oai-service{model:"<model>"}` |
| `harvest_managers` | users who may see this harvester's records and start it |

Loader, transformers and writers are written as `name{options}`, where the options are
a JSON5 object (unquoted keys allowed). Custom readers, transformers and writers can be
registered in `VOCABULARIES_DATASTREAM_READERS` / `_TRANSFORMERS` / `_WRITERS`.

### From the command line

```bash
invenio oai harvesters create \
    --id zenodo --name "Zenodo" \
    --base-url https://zenodo.org/oai2d --metadata-prefix oai_datacite \
    --model datasets \
    --harvest-manager manager@example.org

invenio oai harvesters list            # --json for machine readable output
invenio oai harvesters update zenodo --setspec user-cesnet
invenio oai harvesters delete zenodo
```

`--model` fills in the default transformer and writer for the model; use
`--transformer` / `--writer` (repeatable) to set them explicitly.

### From a fixture

Put `oai_harvesters.yaml` into the instance's `app_data` folder; harvesters are created
(or updated, if they exist) when fixtures are loaded:

```yaml
- id: zenodo
  name: Zenodo
  base-url: https://zenodo.org/oai2d
  metadata-prefix: oai_datacite
  setspec: user-cesnet
  model: datasets
  community: cesnet
  harvest-manager:
    - manager@example.org
```

`transformer` and `writer` default to `oai-import{model:...}` and `oai-service{model:...}`
when `model` is given. Harvest managers are e-mail addresses of existing users.
`community` (optional) is the slug of a community; it is passed as the `community` option
to every `oai-service` writer, so all harvested records are added to that community.

Load (or reload after editing) the fixture with
`invenio rdm-records add-to-fixture oai_harvesters`.

### From the administration UI

*Administration → OAI-PMH Harvesters* lists, creates and edits harvesters.

## Running harvests

```bash
invenio oai harvest zenodo                              # full harvest, in this process
invenio oai harvest zenodo --since 2025-01-01           # records changed since a date
invenio oai harvest zenodo oai:zenodo.org:123 oai:...   # selected records only
invenio oai harvest zenodo --use-job                    # run it as an invenio-jobs job (Celery)
```

Scheduled harvesting uses [invenio-jobs](https://github.com/inveniosoftware/invenio-jobs):

- each harvester has its own job type, `harvest_oaipmh_records_<harvester id>` - create
  a job for it in *Administration → Jobs* and set its schedule. Scheduled runs only
  harvest records changed since the last successful run.
- the job type `run_all_harvesters` runs a full harvest of all harvesters.

A harvest can also be started from the REST API
(`POST /api/oai/harvest/harvesters/<id>/start`), and a single record re-harvested with
`POST /api/oai/harvest/records/<oai identifier>/harvest`.

## The `oai-service` writer

Writes the harvested records through the target model's service. Options:

| Option | Default | Meaning |
|---|---|---|
| `model` | - | target model name (required) |
| `publish` | `true` | publish created / updated drafts. Required for draft-enabled (RDM) models; set `false` only for models without drafts. |
| `direct_update` | `false` | update published records with `service.update` instead of edit - update draft - publish. Only for models whose service allows updating published records. |
| `update_all` | `false` | rewrite every record, even if unchanged since the last harvest |
| `pid_field` | `"id"` | where the record's pid value is in the service result |
| `community` | - | slug (or id) of a community every written record is added to. Only for RDM models. |

### Communities

Written records are added to the writer's `community` and to the communities a
transformer lists in the record's `parent.communities.ids` (slugs or ids), so the
membership can be decided per record:

```python
record["parent"] = {"communities": {"ids": ["cesnet", "another-community"]}}
```

Records are added directly (RDM `bulk_add`), without a community inclusion request; a
subcommunity's parent is added as well, and the community becomes the default one if the
record has none yet.
Communities the record is already in are skipped, and records are never removed from a
community. If a community does not exist, the record is not written and the error is
stored on the harvested record.

Records unchanged since the last harvest are skipped, so after adding a community to an
existing harvester run the harvest with `update_all` to add the already harvested records.

### How records are kept in sync

A record is skipped when its OAI datestamp is unchanged, the last write had no errors
and the local record is still in the harvested state. Otherwise:

| Source says | Local record | Result |
|---|---|---|
| live | missing | created (and published) |
| live | live | updated - a local edit draft is overwritten |
| live | draft only | draft updated and published |
| live | deleted locally (tombstone, also marked for purge) | restored, then updated |
| live | hard deleted | revived from its last revision with the same identifier, then updated |
| deleted | live | deleted - RDM records get a tombstone noting the deletion at the source; a local edit draft is removed |
| deleted | draft only | draft deleted |
| deleted | already deleted | nothing (a left-over local edit draft is removed) |

## Monitoring

Every harvested record is stored as a *harvest record* (keyed by its OAI identifier)
with the OAI datestamp, the deleted flag, the original XML, the transformed data, the
local record identifier and the errors of the last write. Browse them in
*Administration → OAI-PMH Harvester Records* - filter by harvester, deleted flag, error
type, message or location - or via `GET /api/oai/harvest/records`.

## Permissions

- repository administrators can manage all harvesters and see all harvest records;
- harvest managers of a harvester (user ids in `harvest_managers`) can open the
  harvester administration, see the harvester and its harvest records and start it, but
  can not change it.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `OAI_HARVESTER_DEFAULT_BATCH_SIZE` | `1` | records per datastream batch |
| `OAI_HARVESTER_SEARCH`, `OAI_HARVESTER_FACETS`, `OAI_HARVESTER_SORT_OPTIONS` | | search of harvesters |
| `OAI_RECORD_SEARCH`, `OAI_RECORD_FACETS`, `OAI_RECORD_SORT_OPTIONS` | | search of harvest records |

## Development

```bash
./run.sh venv     # create the development environment
./run.sh test     # run the tests (starts the docker services)
./run.sh lint     # format and lint
```

The API documentation is generated from the module docstrings; start with the
`oarepo_oaipmh_harvester` package docstring.

## Custom readers, transformers and writers

Sources that are not plain OAI-PMH endpoints (e.g. a JSON API) or metadata formats your
model can not import can be harvested with your own reader and/or transformer, and
additional writers can act on the harvested records. They are ordinary invenio-vocabularies
datastream classes, registered in `invenio.cfg` and referenced from the harvester's
`loader`, `transformers` and `writers`. What they receive and must produce, how to report
an error for a single record without stopping the harvest, and what is stored on the
harvest record is described, with examples, in
[Readers, transformers and writers](https://oarepo.github.io/oarepo-oaipmh-harvester/readers-transformers-writers.html).

## License

Copyright (c) 2025-2026 CESNET z.s.p.o. Released under the MIT License, see
[LICENSE](LICENSE).
