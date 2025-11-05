from aws_cdk import aws_lambda as _lambda

POWER_TOOLS_PYTHON_RUNTIME = "python312"
LAMBDA_LAYER_NAME = "AWSLambdaPowertoolsPythonV3"
LAMBDA_LAYER_ACCOUNT = "017000801446"
ARCHITECTURE_X86_64 = "x86_64"
POWER_TOOLS_VERSION = "18"
POWER_TOOLS_LAYER = "arn:aws:lambda:{region}:{lambda_layer_account}:layer:{power_tools_type}-{runtime}-{architecture}:{version}"

PYTHON_RUNTIME = _lambda.Runtime.PYTHON_3_12
DEFAULT_ARCHITECTURE = _lambda.Architecture.X86_64
COMMON_LAYER_SRC = "layers/common"
DEFAULT_REGION = "us-east-1"
DEFAULT_ENV = "dev"
GMAIL_SECRET_NAME = "moments_gmail_ingestor_oauth_client_id"
SERVICE_NAME = "moments"
DOMAIN_NAME = "gmail"
ROLE = "ingestor"
