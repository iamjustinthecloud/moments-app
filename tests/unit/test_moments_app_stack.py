import pytest
from aws_cdk.assertions import Template
from aws_cdk import App
from moments_app.moments_app_stack import MomentsAppStack


@pytest.fixture(scope="module")
def template():
    app = App()
    stack = MomentsAppStack(app, "MomentsAppStack")
    template = Template.from_stack(stack)
    return template


# Basic test for now
def test_stack_synthesizes(template):
    # Asserts the template exists by accessing it
    assert template
