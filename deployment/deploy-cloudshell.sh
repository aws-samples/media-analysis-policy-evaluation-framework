# Install Node CDK package
sudo npm install aws-cdk

# Create Python Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Bootstrap CDK - this step will launch a CloudFormation stack to provision the CDK package, which will take ~2 minutes.
cdk bootstrap aws://${CDK_DEFAULT_ACCOUNT}/${CDK_DEFAULT_REGION}
export AWS_DEFAULT_REGION=${CDK_DEFAULT_REGION}

# If variables are empty or unset, set it to the default value
: "${CDK_INPUT_OPENSEARCH_CONFIG:='Dev'}"

echo "cdk deploy --parameters inputUserEmails=${CDK_INPUT_USER_EMAILS} -c env=${CDK_INPUT_OPENSEARCH_CONFIG}  --requires-approval never  --all"
# Deploy CDK package - this step will launch one CloudFormation stack with three nested stacks for different sub-systems.
cdk deploy --parameters inputUserEmails=${CDK_INPUT_USER_EMAILS} -c env=${CDK_INPUT_OPENSEARCH_CONFIG}  --requires-approval never  --all
