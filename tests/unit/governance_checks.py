from stack_test_helpers import find_resources_by_type, get_single_resource_id
from governance_test_helpers import AWSService, resource_governance_doc_url

def assert_s3_compliance(template):
    governance_doc = resource_governance_doc_url(AWSService.S3.value)
    resources = find_resources_by_type(template, "AWS::S3::Bucket")
    logical_id = get_single_resource_id(resources)
    props = resources[logical_id]["Properties"]
    pab = props["PublicAccessBlockConfiguration"]
    assert all(
        value is True for value in pab.values()
    ), ("S3 PublicAccessBlockConfiguration must have all flags set to True "
        f"according to moments security standards. see {governance_doc}")
