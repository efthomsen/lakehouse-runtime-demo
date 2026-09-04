import pytest

from orchestration.submit_batch_job import FloatingImageReference, TaskEnvelope, build_task, require_digest

VALID_DIGEST_REF = "acr.example.io/lakehouse-runtime@sha256:" + "a" * 64


def test_require_digest_accepts_a_pinned_digest():
    assert require_digest(VALID_DIGEST_REF) == VALID_DIGEST_REF


@pytest.mark.parametrize("image", ["acr.example.io/lakehouse-runtime:latest", "acr.example.io/lakehouse-runtime:v1.4.2", "acr.example.io/lakehouse-runtime"])
def test_require_digest_rejects_a_floating_reference(image):
    with pytest.raises(FloatingImageReference):
        require_digest(image)


def _envelope(**overrides) -> TaskEnvelope:
    defaults = dict(
        run_id="RUN-0187",
        image=VALID_DIGEST_REF,
        window_start="2026-09-01T00:00:00Z",
        window_end="2026-09-02T00:00:00Z",
        table_uri="abfss://lake@onelake.dfs.fabric.microsoft.com/bronze/orders_raw",
        git_commit="8a4c1d",
        managed_identity_resource_id="/subscriptions/.../managedIdentities/lakehouse-runtime",
        manifest_uri="abfss://lake@onelake.dfs.fabric.microsoft.com/manifests/RUN-0187.json",
    )
    defaults.update(overrides)
    return TaskEnvelope(**defaults)


def test_build_task_uses_the_pinned_digest_as_the_container_image():
    task = build_task(_envelope())
    assert task["containerSettings"]["imageName"] == VALID_DIGEST_REF


def test_build_task_carries_run_identity_in_the_command_line():
    task = build_task(_envelope())
    assert "--run-id RUN-0187" in task["commandLine"]
    assert "--window-start 2026-09-01T00:00:00Z" in task["commandLine"]
    assert "--window-end 2026-09-02T00:00:00Z" in task["commandLine"]


def test_build_task_environment_carries_git_commit_and_digest():
    task = build_task(_envelope())
    env = {e["name"]: e["value"] for e in task["environmentSettings"]}
    assert env["GIT_COMMIT"] == "8A4C1D"
    assert env["IMAGE_DIGEST"] == VALID_DIGEST_REF


def test_build_task_defaults_to_zero_retries():
    task = build_task(_envelope())
    assert task["constraints"]["maxTaskRetryCount"] == 0


def test_build_task_rejects_a_floating_image_reference():
    envelope = _envelope(image="acr.example.io/lakehouse-runtime:latest")
    with pytest.raises(FloatingImageReference):
        build_task(envelope)
