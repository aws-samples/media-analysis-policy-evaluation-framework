import json
import boto3
import os, time

S3_SWAGGER_BUCKET_NAME = os.environ.get("S3_SWAGGER_BUCKET_NAME")
S3_JS_PREFIX = ''

APIGW_URL_PLACE_HOLDER_EXTR_SRV = os.environ.get("APIGW_URL_PLACE_HOLDER_EXTR_SRV")
APIGW_URL_EXTR_SRV = os.environ.get("APIGW_URL_EXTR_SRV")

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
  s3_response = s3.list_objects(Bucket=S3_SWAGGER_BUCKET_NAME, Prefix="S3_JS_PREFIX")
  if s3_response is not None and "Contents" in s3_response and len(s3_response["Contents"]) > 0:
    for obj in s3_response["Contents"]:
      # Download JS files to the local drive
      file_name = obj["Key"].split('/')[-1]
      print(file_name)
      s3_obj = s3.download_file(S3_SWAGGER_BUCKET_NAME, obj["Key"], f"/tmp/{file_name}")
      
      # read file
      txt = ""
      with open(f"/tmp/{file_name}", 'r') as f:
        txt = f.read()
      if txt is not None and len(txt) > 0:
        # Replace keywords
        txt = txt.replace(APIGW_URL_PLACE_HOLDER_EXTR_SRV, APIGW_URL_EXTR_SRV)
        txt = txt.replace(APIGW_API_KEY_PLACE_HOLDER, APIGW_API_KEY)
        #print(txt)
          
        # Save the file to local disk
        with open(f"/tmp/{file_name}", 'w') as f:
          f.write(txt)
          
        # upload back to s3
        s3.upload_file(f"/tmp/{file_name}", S3_SWAGGER_BUCKET_NAME, obj["Key"])
        
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

    return True

def on_update(event):
  return

def on_delete(event):
  # Cleanup the S3 bucket: web
  s3_res = boto3.resource('s3')
  web_bucket = s3_res.Bucket(S3_SWAGGER_BUCKET_NAME)
  web_bucket.objects.all().delete()

  return True

def on_complete(event):
  return

def is_complete(event):
  return { 'IsComplete': True }