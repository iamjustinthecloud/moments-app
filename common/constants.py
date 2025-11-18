from aws_cdk import aws_lambda as _lambda

POWER_TOOLS_PYTHON_RUNTIME = "python312"
POWER_TOOLS_LAMBDA_LAYER_NAME = "AWSLambdaPowertoolsPythonV3"
POWER_TOOLS_LAMBDA_LAYER_ACCOUNT = "017000801446"
POWER_TOOLS_VERSION = "18"
POWER_TOOLS_ARCHITECTURE = "x86_64"
POWER_TOOLS_LAYER = "arn:aws:lambda:{region}:{lambda_layer_account}:layer:{power_tools_type}-{runtime}-{architecture}:{version}"

PYTHON_RUNTIME = _lambda.Runtime.PYTHON_3_12
DEFAULT_ARCHITECTURE = _lambda.Architecture.X86_64
COMMON_LAYER_SRC = "layers/common"

DEFAULT_ENV = "dev"
GMAIL_RETRIEVER_SECRET_NAME = "moments_gmail_ingestor_oauth_client_id"

# Naming convention components
SERVICE_NAME = "moments"  # The application name
DOMAIN = "gmail"  # The domain being integrated
COMPONENT = "ingestion"  # The functional component/subsystem

# Lambda action types (used in naming)
ACTION_RETRIEVER = "retriever"  # Retrieves data from external source
ACTION_PROCESSOR = "processor"  # Processes data from queue

VPC_NAME = "moments-vpc"
VPC_CIDR = "10.0.0.0/16"
SUBNET_NAME = "moments-subnet"
CIDR_MASK = 24
ANY_IPV4_CIDR = "0.0.0.0/0"
DEFAULT_REGION = "us-east-1"
