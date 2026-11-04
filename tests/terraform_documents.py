"""Small, fictional Terraform documents in the shape Terraform writes them, for the tests that hand the engine a
state or a plan. Every identifier is a placeholder (`00000000-0000-0000-0000-000000000001`, `hcw-sample-*`).

A state (version 4) lists `resources[]`, each with `instances[]` carrying `attributes` and the paths Terraform marked
sensitive. A plan (`terraform show -json`, format 1.x) lists `resource_changes[]`, each with `change.after` (the
values after the change), `change.after_unknown` (what is only known after apply) and `change.after_sensitive`.
"""

from __future__ import annotations

from typing import Any

SUB = "00000000-0000-0000-0000-000000000001"
GROUP = "rg-hcw-sample-prod"
PROVIDER = 'provider["registry.terraform.io/hashicorp/azurerm"]'
PROVIDER_NAME = "registry.terraform.io/hashicorp/azurerm"


def arm_id(namespace: str, kind: str, name: str, *more: str) -> str:
    return f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/{'/'.join([namespace, kind, name, *more])}"


def storage_attributes(name: str, replication: str = "ZRS", *, tags: dict[str, str] | None = None) -> dict[str, Any]:
    """A storage account as azurerm writes it; `ZRS` is zone redundant, `LRS` is not."""
    return {
        "id": arm_id("Microsoft.Storage", "storageAccounts", name),
        "name": name,
        "resource_group_name": GROUP,
        "location": "centralus",
        "account_tier": "Standard",
        "account_replication_type": replication,
        "public_network_access_enabled": False,
        "identity": [],
        "tags": {"env": "prod"} if tags is None else tags,
    }


def sql_database_attributes(name: str, *, zone_redundant: bool) -> dict[str, Any]:
    server = arm_id("Microsoft.Sql", "servers", "hcw-sample-sqlsrv-02")
    return {
        "id": f"{server}/databases/{name}",
        "name": name,
        "server_id": server,
        "sku_name": "GP_Gen5_2",
        "zone_redundant": zone_redundant,
        "identity": [],
        "tags": {"env": "prod"},
    }


def state_record(
    terraform_type: str,
    name: str,
    attributes: dict[str, Any],
    *,
    sensitive: list[list[dict[str, Any]]] | None = None,
    mode: str = "managed",
) -> dict[str, Any]:
    return {
        "mode": mode,
        "type": terraform_type,
        "name": name,
        "provider": PROVIDER,
        "instances": [{"schema_version": 0, "attributes": attributes, "sensitive_attributes": sensitive or []}],
    }


def state_of(*records: dict[str, Any]) -> dict[str, Any]:
    return {"version": 4, "terraform_version": "1.9.8", "serial": 1, "lineage": "x", "resources": list(records)}


def change_entry(
    terraform_type: str,
    name: str,
    after: dict[str, Any] | None,
    *,
    actions: tuple[str, ...] = ("no-op",),
    unknown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "address": f"{terraform_type}.{name}",
        "mode": "managed",
        "type": terraform_type,
        "name": name,
        "provider_name": PROVIDER_NAME,
        "change": {
            "actions": list(actions),
            "before": None,
            "after": after,
            "after_unknown": unknown or {},
            "before_sensitive": False,
            "after_sensitive": {},
        },
    }


def plan_of(*changes: dict[str, Any]) -> dict[str, Any]:
    return {"format_version": "1.2", "terraform_version": "1.9.8", "resource_changes": list(changes)}


def sample_state() -> dict[str, Any]:
    """Two mapped rows (a zone-redundant storage account, a SQL database that is not), a resource group the engine's
    type table does not map, and a data source. The storage account's key is marked sensitive, as Terraform does."""
    return state_of(
        state_record(
            "azurerm_resource_group",
            "prod",
            {"id": f"/subscriptions/{SUB}/resourceGroups/{GROUP}", "name": GROUP, "location": "centralus"},
        ),
        state_record(
            "azurerm_storage_account",
            "prod",
            {**storage_attributes("hcwsamplestprod02"), "primary_access_key": "fictional-placeholder"},
            sensitive=[[{"type": "get_attr", "value": "primary_access_key"}]],
        ),
        state_record(
            "azurerm_mssql_database", "sql", sql_database_attributes("hcw-sample-sql-02", zone_redundant=False)
        ),
        state_record("azurerm_client_config", "current", {"id": "x"}, mode="data"),
    )


TAGS_AFTER_APPLY = {"tags": {"env": True}}  # `after_unknown` for a tag whose value is only known after apply


def sample_plan() -> dict[str, Any]:
    """Four changes: a SQL database the plan updates to zone redundant (it has an Azure id); a storage account the plan
    creates (no Azure id yet, so it is outside any decision scoped to a subscription); a zone-redundant storage account
    the plan updates whose `env` tag is only known after apply (`after` has lost the entry and `after_unknown` says
    why); and a key vault the plan destroys, which makes no row."""
    created = storage_attributes("hcwsamplestlogs02", tags={})
    del created["id"]
    return plan_of(
        change_entry(
            "azurerm_mssql_database",
            "sql",
            sql_database_attributes("hcw-sample-sql-02", zone_redundant=True),
            actions=("update",),
        ),
        change_entry(
            "azurerm_storage_account", "logs", created, actions=("create",), unknown={"id": True, **TAGS_AFTER_APPLY}
        ),
        change_entry(
            "azurerm_storage_account",
            "prod",
            storage_attributes("hcwsamplestprod02", tags={}),
            actions=("update",),
            unknown=TAGS_AFTER_APPLY,
        ),
        change_entry("azurerm_key_vault", "old", None, actions=("delete",)),
    )
