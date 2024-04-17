import json
import boto3
import os, time

S3_WEB_BUCKET_NAME = os.environ.get("S3_WEB_BUCKET_NAME")
S3_JS_PREFIX = 'static/js/'

APIGW_URL_PLACE_HOLDER_EXTR_SRV = os.environ.get("APIGW_URL_PLACE_HOLDER_EXTR_SRV")
APIGW_URL_PLACE_HOLDER_EVAL_SRV = os.environ.get("APIGW_URL_PLACE_HOLDER_EVAL_SRV")
COGNITO_USER_POOL_ID_PLACE_HOLDER = os.environ.get("COGNITO_USER_POOL_ID_PLACE_HOLDER")
COGNITO_USER_IDENTITY_POOL_ID_PLACE_HOLDER = os.environ.get("COGNITO_USER_IDENTITY_POOL_ID_PLACE_HOLDER")
COGNITO_REGION_PLACE_HOLDER = os.environ.get("COGNITO_REGION_PLACE_HOLDER")
COGNITO_USER_POOL_CLIENT_ID_PLACE_HOLDER = os.environ.get("COGNITO_USER_POOL_CLIENT_ID_PLACE_HOLDER")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")
COGNITO_USER_POOL_CLIENT_ID = os.environ.get("COGNITO_USER_POOL_CLIENT_ID")
COGNITO_USER_EMAILS = os.environ.get("COGNITO_USER_EMAILS")
COGNITO_INVITATION_EMAIL_TEMPLATE = os.environ.get("COGNITO_INVITATION_EMAIL_TEMPLATE")
COGNITO_INVITATION_EMAIL_TITLE = os.environ.get("COGNITO_INVITATION_EMAIL_TITLE")
CLOUD_FRONT_URL = os.environ.get("CLOUD_FRONT_URL")
APP_NAME = os.environ.get("APP_NAME")
BASTION_HOST_ID = os.environ.get("BASTION_HOST_ID")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
SSM_INSTRUCTION_URL= os.environ.get("SSM_INSTRUCTION_URL")

APIGW_URL_EXTR_SRV = os.environ.get("APIGW_URL_EXTR_SRV")
APIGW_URL_EVAL_SRV = os.environ.get("APIGW_URL_EVAL_SRV")
COGNITO_REGION = os.environ.get("COGNITO_REGION")
COGNITO_USER_IDENTITY_POOL_ID = os.environ.get("COGNITO_USER_IDENTITY_POOL_ID")

CLOUD_FRONT_DISTRIBUTION_ID = os.environ.get("CLOUD_FRONT_DISTRIBUTION_ID")

s3 = boto3.client('s3')
cloudfront = boto3.client('cloudfront')
cognito = boto3.client('cognito-idp')

def on_event(event, context):
  print(event)
  request_type = event['RequestType']
  if request_type == 'Create': return on_create(event)
  if request_type == 'Update': return on_update(event)
  if request_type == 'Delete': return on_delete(event)
  raise Exception("Invalid request type: %s" % request_type)

def on_create(event):
  # Get files from s3 buckets
  s3_response = s3.list_objects(Bucket=S3_WEB_BUCKET_NAME, Prefix=S3_JS_PREFIX)
  if s3_response is not None and "Contents" in s3_response and len(s3_response["Contents"]) > 0:
    for obj in s3_response["Contents"]:
      # Download JS files to the local drive
      file_name = obj["Key"].split('/')[-1]
      print(file_name)
      s3_obj = s3.download_file(S3_WEB_BUCKET_NAME, obj["Key"], f"/tmp/{file_name}")
      
      # read file
      txt = ""
      with open(f"/tmp/{file_name}", 'r') as f:
        txt = f.read()
      if txt is not None and len(txt) > 0:
        # Replace keywords
        txt = txt.replace(APIGW_URL_PLACE_HOLDER_EXTR_SRV, APIGW_URL_EXTR_SRV)
        txt = txt.replace(APIGW_URL_PLACE_HOLDER_EVAL_SRV, APIGW_URL_EVAL_SRV)
        txt = txt.replace(COGNITO_USER_POOL_ID_PLACE_HOLDER, COGNITO_USER_POOL_ID)
        txt = txt.replace(COGNITO_USER_IDENTITY_POOL_ID_PLACE_HOLDER, COGNITO_USER_IDENTITY_POOL_ID)
        txt = txt.replace(COGNITO_REGION_PLACE_HOLDER, COGNITO_REGION)
        txt = txt.replace(COGNITO_USER_POOL_CLIENT_ID_PLACE_HOLDER, COGNITO_USER_POOL_CLIENT_ID)
        #print(txt)
          
        # Save the file to local disk
        with open(f"/tmp/{file_name}", 'w') as f:
          f.write(txt)
          
        # upload back to s3
        s3.upload_file(f"/tmp/{file_name}", S3_WEB_BUCKET_NAME, obj["Key"])
        
        # delete local file
        os.remove(f"/tmp/{file_name}")
    
    # Invalidate CloudFront
    cloudfront.create_invalidation(
      DistributionId=CLOUD_FRONT_DISTRIBUTION_ID,
      InvalidationBatch={
              'Paths': {
                  'Quantity': 1,
                  'Items': [
                      '/*',
                  ]
              },
              'CallerReference': 'CDK auto website deployment'
          }
      )

    # Update Cognitio Invitation Email template
    try:
      email_body = COGNITO_INVITATION_EMAIL_TEMPLATE.replace("##CLOUDFRONT_URL##", CLOUD_FRONT_URL) \
                    .replace("##APP_NAME##", APP_NAME) \
                    .replace("##BASTION_HOST_ID##", BASTION_HOST_ID) \
                    .replace("##OPENSEARCH_DOMAIN_ENDPOINT##",OPENSEARCH_DOMAIN_ENDPOINT) \
                    .replace("##SSM_INSTRUCTION_URL##",SSM_INSTRUCTION_URL)
      email_title = COGNITO_INVITATION_EMAIL_TITLE.replace("##APP_NAME##", APP_NAME)
      response = cognito.update_user_pool(
          UserPoolId=COGNITO_USER_POOL_ID,
          AdminCreateUserConfig={
            'InviteMessageTemplate': {
                #'SMSMessage': 'string',
                'EmailMessage': email_body,
                'EmailSubject': email_title
            }
          }
      )
      print(response)
    except Exception as ex:
      print("Failed to update email template:", ex)

    # Add users to Cognito user pool
    if COGNITO_USER_EMAILS is not None and len(COGNITO_USER_EMAILS) > 0:
      for email in COGNITO_USER_EMAILS.split(','):
        try:
          cognito.admin_create_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=email,
            UserAttributes=[
              {
                  'Name': 'email',
                  'Value': email
              },
            ],
            DesiredDeliveryMediums=['EMAIL'],
          )
        except Exception as ex:
          print(ex)
    
    # Add sample global rule to DynamoDB
    #if DYNAMO_DEFAULT_GLOBAL_RULE is not None:
    #  default_rule = json.loads(DYNAMO_DEFAULT_GLOBAL_RULE)
    #  if default_rule is not None:
    #    response = config_table.put_item(Item=default_rule)    

    return True

def on_update(event):
  return

def on_delete(event):
  # Cleanup the S3 bucket: web
  s3_res = boto3.resource('s3')
  web_bucket = s3_res.Bucket(S3_WEB_BUCKET_NAME)
  web_bucket.objects.all().delete()

  return True

def on_complete(event):
  return

def is_complete(event):
  return { 'IsComplete': True }