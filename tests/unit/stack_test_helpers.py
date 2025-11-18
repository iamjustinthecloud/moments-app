from dataclasses import dataclass
from typing import Any, Mapping, Optional
from aws_cdk.assertions import Match, Template
from moments_app.moments_app_stack import MomentsAppStack
from aws_cdk import App
import pytest


# ------------------- Test Case Data Classes -------------------
@dataclass(frozen=True)
class LambdaTestCase:
    id: str
    function_name: str
    handler: str
    memory_size: int
    timeout: int
    extra_env: Mapping[str, Any]


@dataclass(frozen=True)
class LogGroupTestCase:
    id: str
    log_group_name: str
    retention_days: int


@dataclass(frozen=True)
class UpdateDeletePolicyTestCase:
    id: str
    update_policy: str
    delete_policy: str


# ------------------- Helper Functions -------------------


def find_resources_by_type(
    template: Template, resource_type: str, props: Optional[dict] = None
) -> Mapping[str, Any]:

    return template.find_resources(resource_type, props=props)


def get_single_resource_id(
    resources: Mapping[str, Any], resource_type: str = "resource"
) -> str:
    return next(iter(resources))


def build_template(stack_id: str = "TestMomentsAppStack"):
    app = App()
    stack = MomentsAppStack(app, stack_id)
    return Template.from_stack(stack)


# ------------------- Pytest Fixtures -------------------


@pytest.fixture
def template() -> Template:
    return build_template()


@pytest.fixture
def json_template(template: Template) -> Mapping[str, Any]:
    return template.to_json()


def expected_lambda_props(case: LambdaTestCase) -> Mapping[str, Any]:
    return {
        "FunctionName": Match.string_like_regexp(case.function_name),
        "Handler": case.handler,
        "Runtime": "python3.12",
        "MemorySize": case.memory_size,
        "Timeout": case.timeout,
        "Architectures": ["x86_64"],
        "Code": {
            "S3Bucket": Match.any_value(),
            "S3Key": Match.any_value(),
        },
        "TracingConfig": {"Mode": "Active"},
        "Environment": {
            "Variables": {"SECRET_NAME": Match.any_value(), **case.extra_env}
        },
    }
