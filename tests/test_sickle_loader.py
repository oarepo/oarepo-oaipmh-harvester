import pytest

from oarepo_oaipmh_harvester.readers.sickle import SickleReader


def test_sickle_loader_first_record():
    loader = SickleReader(
        oai_config={"setspecs": "user-openaire", "metadataprefix": "oai_dc"},
        source="https://zenodo.org/oai2d",
        datestamp_from="2020-01-20",
        datestamp_until="2020-01-21",
    )
    iterator = iter(loader)
    item = next(iterator)

    assert item.context["oai"]["datestamp"].startswith("2020-01-20T")
    assert "metadata" in item.context["oai"]
    assert "title" in item.context["oai"]["metadata"]


def test_sickle_loader_single_record():
    loader = SickleReader(
        oai_config={"setspecs": "user-openaire", "metadataprefix": "oai_dc"},
        source="https://zenodo.org/oai2d",
        identifiers=["oai:zenodo.org:59204"],
    )
    iterator = iter(loader)
    item = next(iterator)
    print(item)
    assert item.context["oai"] == {
        "datestamp": "2024-08-04T03:17:18+00:00",
        "deleted": False,
        "identifier": "oai:zenodo.org:59204",
        "oai_url": "https://zenodo.org/oai2d",
        "metadata": {
            "creator": ["van Berchum, Marnix", "Rodrigues, Eloy"],
            "date": ["2010-07-29"],
            "description": [
                "&lt;p&gt;The OpenAIRE Guidelines 1.0 will "
                "provide orientation for repository managers to "
                "define and implement their local data "
                "management policies in compliance with the Open "
                "Access demands of the European Commission. "
                "Furthermore they will comply with the technical "
                "requirements of the OpenAIRE infrastructure "
                "that is being established to support and "
                "monitor the implementation of the FP7 OA "
                "pilot.&lt;br&gt;\n"
                "By implementing these Guidelines repository "
                "managers are facilitating the authors who "
                "deposit their publications in the repository, "
                "in complying with the EC Open Access "
                "requirements.&lt;br&gt;\n"
                "For developers of repository platforms the "
                "Guidelines provide guidance to add supportive "
                "functionalities for authors of EC funded "
                "research in future versions.&lt;/p&gt;"
            ],
            "identifier": [
                "https://doi.org/10.5281/zenodo.59204",
                "oai:zenodo.org:59204",
            ],
            "publisher": ["Zenodo"],
            "relation": [
                "https://zenodo.org/communities/openaire/",
                "https://zenodo.org/communities/eu/",
                "https://doi.org/",
            ],
            "rights": [
                "info:eu-repo/semantics/openAccess",
                "Creative Commons Attribution Share Alike 4.0 International",
                "https://creativecommons.org/licenses/by-sa/4.0/legalcode",
            ],
            "subject": ["Repository", "Open Access", "Guidelines"],
            "title": [
                "OpenAIRE Guidelines 1.0 : Guidelines for content "
                "providers of the OpenAIRE information space"
            ],
            "type": ["info:eu-repo/semantics/report"],
        },
        "setSpecs": ["user-openaire", "user-eu"],
    }
    with pytest.raises(StopIteration):
        next(iterator)
